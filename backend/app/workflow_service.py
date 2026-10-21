"""Workflow orchestration with Groq suggestions and backend-controlled simulations."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_service import GroqHelpdeskService
from app.knowledge_base import retrieve_articles
from app.models import Ticket, WorkflowEvent, WorkflowRun
from app.schemas import WorkflowDiagnosis
from app.workflow_tools import ALLOWED_TOOLS, execute_simulated_tool, select_tool


class WorkflowTicketNotFound(Exception):
    pass


def add_event(db: Session, run: WorkflowRun, stage: str, status: str, detail: str, evidence: dict | None = None) -> None:
    db.add(WorkflowEvent(workflow_id=run.id, stage=stage, status=status, detail=detail, evidence=evidence or {}))


def start_workflow(
    db: Session,
    issue: str,
    ticket_id: str | None,
    ai: GroqHelpdeskService,
    owner_user_id: str,
) -> WorkflowRun:
    if ticket_id and db.get(Ticket, ticket_id) is None:
        raise WorkflowTicketNotFound

    sources = retrieve_articles(issue)
    diagnosis: WorkflowDiagnosis = ai.diagnose(issue, sources)
    tool_name = select_tool(issue, diagnosis.category.value)
    if tool_name not in ALLOWED_TOOLS:
        # Defense in depth; selector output must still be an allowlisted tool.
        raise ValueError("Selected tool is not permitted.")
    simulated = execute_simulated_tool(tool_name, issue)
    verification = {
        "criterion": "The deterministic simulated output matches the expected demonstration response.",
        "passed": simulated.passed,
        "reason": simulated.reason,
        "real_environment_verified": False,
    }
    if simulated.passed is True:
        workflow_status = "awaiting_user"
        proposed_resolution = "Try the recommended troubleshooting steps and check whether the original symptom stops. This is a suggestion only; no live device state has been verified or changed."
        next_action = "Try the suggested steps in your own environment, then confirm whether the issue is fixed. This simulation did not verify your device."
        verification["outcome"] = "sample_passed_user_confirmation_required"
    else:
        workflow_status = "needs_escalation"
        proposed_resolution = "A safe resolution cannot be proposed from this inconclusive simulated check. Campus IT should verify the issue."
        next_action = "Contact campus IT and include the simulated result and the issue details. No ticket was created automatically."
        verification["outcome"] = "inconclusive_escalate"

    run = WorkflowRun(
        issue=issue,
        status=workflow_status,
        current_stage="awaiting_user" if workflow_status == "awaiting_user" else "escalation_recommended",
        diagnosis=diagnosis.model_dump(mode="json"),
        sources=[{"title": article.title, "category": article.category} for article in sources],
        tool_name=tool_name,
        tool_input={"issue_summary": diagnosis.summary, "label": "SIMULATED INPUT ONLY"},
        tool_output=simulated.output,
        verification=verification,
        proposed_resolution=proposed_resolution,
        next_action=next_action,
        ticket_id=ticket_id,
        user_id=owner_user_id,
    )
    db.add(run)
    db.flush()
    add_event(db, run, "issue_received", "complete", "Issue received for a safe troubleshooting workflow.", {"ticket_id": ticket_id})
    add_event(db, run, "ai_diagnosis", "complete", "Groq generated a suggested diagnosis; it is not a verified fact.", run.diagnosis)
    add_event(db, run, "knowledge_lookup", "complete", f"Retrieved {len(sources)} matching knowledge-base article(s).", {"sources": run.sources})
    add_event(db, run, "simulated_tool", "complete", f"{ALLOWED_TOOLS[tool_name]} ran as a deterministic simulation only.", run.tool_output)
    add_event(db, run, "verification", "passed" if simulated.passed is True else "inconclusive", simulated.reason, verification)
    if simulated.passed is not True:
        add_event(db, run, "escalation", "recommended", "Human verification is required; no ticket was created automatically.", {"ticket_id": ticket_id})
    db.commit()
    db.refresh(run)
    return run


def serialize_workflow(db: Session, run: WorkflowRun) -> dict:
    events = db.scalars(select(WorkflowEvent).where(WorkflowEvent.workflow_id == run.id).order_by(WorkflowEvent.created_at, WorkflowEvent.id)).all()
    return {
        "id": run.id,
        "issue": run.issue,
        "status": run.status,
        "current_stage": run.current_stage,
        "diagnosis": run.diagnosis,
        "sources": run.sources,
        "tool_name": run.tool_name,
        "tool_input": run.tool_input,
        "tool_output": run.tool_output,
        "verification": run.verification,
        "proposed_resolution": run.proposed_resolution,
        "next_action": run.next_action,
        "ticket_id": run.ticket_id,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "events": [
            {"stage": event.stage, "status": event.status, "detail": event.detail, "evidence": event.evidence, "created_at": event.created_at}
            for event in events
        ],
    }


def confirm_workflow(db: Session, run: WorkflowRun, fixed: bool) -> WorkflowRun:
    if run.status != "awaiting_user":
        raise ValueError("This workflow is not awaiting user confirmation.")
    if fixed:
        run.status = "user_confirmed_resolved"
        run.current_stage = "user_confirmation"
        run.next_action = "The user confirmed the issue is fixed. Any linked ticket remains unchanged and must follow its own supported resolution process."
        add_event(db, run, "user_confirmation", "confirmed", "User confirmed the issue is fixed.", {"ticket_id": run.ticket_id})
    else:
        run.status = "needs_escalation"
        run.current_stage = "escalation_recommended"
        run.next_action = "Contact campus IT and include the workflow evidence. Create or link a ticket only if needed; no ticket was created automatically."
        add_event(db, run, "user_confirmation", "not_fixed", "User reported that the issue is not fixed.", {"ticket_id": run.ticket_id})
        add_event(db, run, "escalation", "recommended", "Human support is recommended based on the user's confirmation.", {"ticket_id": run.ticket_id})
    db.commit()
    db.refresh(run)
    return run
