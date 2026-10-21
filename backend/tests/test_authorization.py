from contextlib import ExitStack
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.auth_security import hash_password
from app.main import app, get_groq_service
from app.models import Ticket, TicketCategory, TicketPriority, TicketStatus, User, WorkflowEvent, WorkflowRun
from app.schemas import WorkflowDiagnosis


ORIGIN = "http://localhost:5173"


def create_account(test_db, identity: str, role: str = "user") -> str:
    with test_db() as db:
        user = User(login_identity=identity, password_hash=hash_password("isolated test password"), role=role)
        db.add(user)
        db.commit()
        return user.id


def login(client: TestClient, identity: str) -> str:
    token = client.get("/api/auth/csrf", headers={"Origin": ORIGIN}).json()["csrf_token"]
    response = client.post(
        "/api/auth/login",
        json={"login_identity": identity, "password": "isolated test password"},
        headers={"Origin": ORIGIN, "X-CSRF-Token": token},
    )
    assert response.status_code == 200
    return response.json()["user"]["id"]


def csrf_headers(client: TestClient) -> dict[str, str]:
    return {"Origin": ORIGIN, "X-CSRF-Token": client.cookies.get("helpdesk_csrf", "")}


def ticket_payload(title: str, **overrides) -> dict:
    return {
        "title": title,
        "description": f"Private description for {title} that must stay scoped.",
        "category": "Network",
        "priority": "High",
        "owner": "Spoofed owner from browser",
        **overrides,
    }


class FakeDiagnosisService:
    def diagnose(self, issue, sources):
        return WorkflowDiagnosis(
            summary="Intermittent network connectivity issue",
            category="Network",
            suggested_priority="Medium",
            likely_causes=["Weak signal"],
            troubleshooting_steps=["Check signal strength in another location."],
        )


def create_run(db, user_id: str | None, issue: str, ticket_id: str | None = None) -> WorkflowRun:
    run = WorkflowRun(
        issue=issue,
        status="awaiting_user",
        current_stage="awaiting_user",
        diagnosis={
            "summary": "Private diagnosis for this user",
            "category": "Network",
            "suggested_priority": "Medium",
            "likely_causes": ["Private cause"],
            "troubleshooting_steps": ["Private step"],
        },
        sources=[],
        tool_name="simulated_network_connectivity",
        tool_input={"label": "SIMULATED INPUT ONLY"},
        tool_output={"label": "SIMULATED", "result": "test"},
        verification={"passed": True, "real_environment_verified": False},
        proposed_resolution="Suggestion only",
        next_action="Confirm after trying steps",
        ticket_id=ticket_id,
        user_id=user_id,
    )
    db.add(run)
    db.flush()
    db.add(WorkflowEvent(workflow_id=run.id, stage="private_test_event", status="complete", detail="Private audit detail", evidence={"private": True}))
    db.commit()
    db.refresh(run)
    return run


def test_protected_routes_reject_anonymous_requests_and_health_remains_public(client):
    csrf = client.get("/api/auth/csrf", headers={"Origin": ORIGIN}).json()["csrf_token"]
    csrf_headers_anonymous = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
    protected_reads = [
        "/api/tickets",
        "/api/tickets/HD-UNKNOWN1",
        "/api/workflows",
        "/api/workflows/unknown-workflow",
        "/api/dashboard",
        "/api/auth/me",
        "/openapi.json",
        "/docs",
        "/redoc",
    ]
    for path in protected_reads:
        assert client.get(path).status_code == 401, path

    protected_writes = [
        ("POST", "/api/tickets", ticket_payload("Anonymous ticket")),
        ("PATCH", "/api/tickets/HD-UNKNOWN1", {"title": "Anonymous update"}),
        ("POST", "/api/ai/chat", {"issue": "Laptop will not connect to Wi-Fi"}),
        ("POST", "/api/workflows", {"issue": "Laptop will not connect to Wi-Fi"}),
        ("POST", "/api/workflows/unknown-workflow/confirm", {"fixed": True}),
    ]
    for method, path, payload in protected_writes:
        assert client.request(method, path, json=payload, headers=csrf_headers_anonymous).status_code == 401, path

    assert client.get("/api/health").status_code == 200


def test_authenticated_cookie_mutations_require_csrf(test_db):
    create_account(test_db, "csrf-user@example.edu")
    with TestClient(app) as client:
        login(client, "csrf-user@example.edu")
        requests = [
            ("POST", "/api/tickets", ticket_payload("CSRF ticket")),
            ("PATCH", "/api/tickets/HD-MISSING1", {"title": "Updated title"}),
            ("POST", "/api/ai/chat", {"issue": "Wi-Fi is not connecting"}),
            ("POST", "/api/workflows", {"issue": "Wi-Fi is not connecting"}),
            ("POST", "/api/workflows/missing-run/confirm", {"fixed": True}),
        ]
        for method, url, body in requests:
            response = client.request(method, url, json=body, headers={"Origin": ORIGIN})
            assert response.status_code == 403, url


def test_ticket_scope_creation_spoofing_and_admin_cross_user_access(test_db):
    create_account(test_db, "user-a@example.edu")
    create_account(test_db, "user-b@example.edu")
    create_account(test_db, "admin@example.edu", "admin")
    with ExitStack() as stack:
        a, b, admin = (stack.enter_context(TestClient(app)) for _ in range(3))
        user_a_id = login(a, "user-a@example.edu")
        user_b_id = login(b, "user-b@example.edu")
        login(admin, "admin@example.edu")

        ticket_a = a.post("/api/tickets", json=ticket_payload("A private network issue"), headers=csrf_headers(a)).json()
        ticket_b = b.post("/api/tickets", json=ticket_payload("B private account issue", category="Account"), headers=csrf_headers(b)).json()
        attempted_user_id_spoof = a.post(
            "/api/tickets", json=ticket_payload("Spoofed ownership", user_id=user_b_id), headers=csrf_headers(a)
        )
        assert attempted_user_id_spoof.status_code == 422
        assert ticket_a["owner"] == "user-a@example.edu"
        assert ticket_b["owner"] == "user-b@example.edu"

        with test_db() as db:
            assert db.get(Ticket, ticket_a["id"]).user_id == user_a_id
            assert db.get(Ticket, ticket_b["id"]).user_id == user_b_id
            historical = Ticket(
                id="HD-HIST0001", title="Unlinked historical ticket", description="Historical details are admin-only.",
                category=TicketCategory.other, priority=TicketPriority.low, status=TicketStatus.open,
                owner="Historical owner text", user_id=None,
            )
            db.add(historical)
            db.commit()

        assert [row["id"] for row in a.get("/api/tickets").json()] == [ticket_a["id"]]
        assert a.get("/api/tickets", params={"search": "B private"}).json() == []
        foreign_ticket = a.get(f"/api/tickets/{ticket_b['id']}")
        missing_ticket = a.get("/api/tickets/HD-NOTREAL1")
        assert foreign_ticket.status_code == missing_ticket.status_code == 404
        assert foreign_ticket.json() == missing_ticket.json()
        assert a.get("/api/tickets/HD-HIST0001").status_code == 404
        foreign_patch = a.patch(f"/api/tickets/{ticket_b['id']}", json={"title": "Changed by A"}, headers=csrf_headers(a))
        missing_patch = a.patch("/api/tickets/HD-NOTREAL1", json={"title": "Changed by A"}, headers=csrf_headers(a))
        assert foreign_patch.status_code == missing_patch.status_code == 404
        assert foreign_patch.json() == missing_patch.json()
        assert a.patch(f"/api/tickets/{ticket_a['id']}", json={"status": "Resolved"}, headers=csrf_headers(a)).status_code == 403
        assert a.patch(f"/api/tickets/{ticket_a['id']}", json={"user_id": user_b_id}, headers=csrf_headers(a)).status_code == 422

        all_tickets = admin.get("/api/tickets").json()
        assert {row["id"] for row in all_tickets} == {ticket_a["id"], ticket_b["id"], "HD-HIST0001"}
        assert admin.get(f"/api/tickets/{ticket_b['id']}").status_code == 200
        changed = admin.patch(f"/api/tickets/{ticket_b['id']}", json={"status": "Resolved", "resolution": "Restored access and confirmed the requester can sign in."}, headers=csrf_headers(admin))
        assert changed.status_code == 200
        assert changed.json()["status"] == "Resolved"


def test_user_owned_ticket_edits_are_limited_to_nonprivileged_fields(user_client):
    created = user_client.post("/api/tickets", json=ticket_payload("My campus network issue"))
    assert created.status_code == 201
    updated = user_client.patch(
        f"/api/tickets/{created.json()['id']}",
        json={"title": "My updated campus issue"},
        headers=csrf_headers(user_client),
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "My updated campus issue"
    assert user_client.patch(
        f"/api/tickets/{created.json()['id']}", json={"priority": "Low"}, headers=csrf_headers(user_client)
    ).status_code == 403


def test_api_docs_and_openapi_require_a_session_and_work_for_authenticated_clients(admin_client):
    assert admin_client.get("/docs").status_code == 200
    assert admin_client.get("/redoc").status_code == 200
    schema = admin_client.get("/openapi.json")
    assert schema.status_code == 200
    assert "/api/tickets" in schema.json()["paths"]


def test_workflow_ownership_link_validation_confirmation_and_admin_access(test_db):
    create_account(test_db, "workflow-a@example.edu")
    create_account(test_db, "workflow-b@example.edu")
    create_account(test_db, "workflow-admin@example.edu", "admin")
    with ExitStack() as stack:
        a, b, admin = (stack.enter_context(TestClient(app)) for _ in range(3))
        id_a = login(a, "workflow-a@example.edu")
        id_b = login(b, "workflow-b@example.edu")
        admin_id = login(admin, "workflow-admin@example.edu")

        ticket_a = a.post("/api/tickets", json=ticket_payload("A linked network ticket"), headers=csrf_headers(a)).json()
        ticket_b = b.post("/api/tickets", json=ticket_payload("B linked network ticket"), headers=csrf_headers(b)).json()
        app.dependency_overrides[get_groq_service] = lambda: FakeDiagnosisService()

        run_a = a.post("/api/workflows", json={"issue": "A has intermittent Wi-Fi", "ticket_id": ticket_a["id"]}, headers=csrf_headers(a))
        run_b = b.post("/api/workflows", json={"issue": "B has intermittent Wi-Fi", "ticket_id": ticket_b["id"]}, headers=csrf_headers(b))
        assert run_a.status_code == run_b.status_code == 201
        a_run, b_run = run_a.json(), run_b.json()
        with test_db() as db:
            historical_run = create_run(db, None, "Unlinked historical workflow")

        with test_db() as db:
            assert db.get(WorkflowRun, a_run["id"]).user_id == id_a
            assert db.get(WorkflowRun, b_run["id"]).user_id == id_b
            mismatched_link_run = create_run(db, id_a, "A-owned run with an inconsistent foreign ticket link", ticket_b["id"])

        denied_link = a.post("/api/workflows", json={"issue": "A cannot use B ticket", "ticket_id": ticket_b["id"]}, headers=csrf_headers(a))
        assert denied_link.status_code == 404
        assert [row["id"] for row in a.get("/api/workflows").json()] == [a_run["id"]]
        foreign_workflow = a.get(f"/api/workflows/{b_run['id']}")
        missing_workflow = a.get("/api/workflows/nonexistent-workflow")
        assert foreign_workflow.status_code == missing_workflow.status_code == 404
        assert foreign_workflow.json() == missing_workflow.json()
        assert a.get(f"/api/workflows/{mismatched_link_run.id}").status_code == 404
        foreign_confirmation = a.post(f"/api/workflows/{b_run['id']}/confirm", json={"fixed": True}, headers=csrf_headers(a))
        missing_confirmation = a.post("/api/workflows/nonexistent-workflow/confirm", json={"fixed": True}, headers=csrf_headers(a))
        assert foreign_confirmation.status_code == missing_confirmation.status_code == 404
        assert foreign_confirmation.json() == missing_confirmation.json()

        confirmed = a.post(f"/api/workflows/{a_run['id']}/confirm", json={"fixed": True}, headers=csrf_headers(a))
        assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "user_confirmed_resolved"
        assert confirmed.json()["events"][-1]["stage"] == "user_confirmation"
        admin_linked_run = admin.post(
            "/api/workflows", json={"issue": "Admin investigates B's network ticket", "ticket_id": ticket_b["id"]}, headers=csrf_headers(admin)
        )
        assert admin_linked_run.status_code == 201
        with test_db() as db:
            assert db.get(WorkflowRun, admin_linked_run.json()["id"]).user_id == admin_id
        assert {row["id"] for row in admin.get("/api/workflows").json()} == {
            a_run["id"], b_run["id"], mismatched_link_run.id, historical_run.id, admin_linked_run.json()["id"]
        }
        admin_view = admin.get(f"/api/workflows/{b_run['id']}")
        assert admin_view.status_code == 200
        assert any(event["stage"] == "simulated_tool" for event in admin_view.json()["events"])


def test_dashboard_metrics_and_activity_are_scoped_with_unlinked_history_admin_only(test_db):
    create_account(test_db, "dashboard-a@example.edu")
    create_account(test_db, "dashboard-b@example.edu")
    create_account(test_db, "dashboard-admin@example.edu", "admin")
    with ExitStack() as stack:
        a, b, admin = (stack.enter_context(TestClient(app)) for _ in range(3))
        id_a = login(a, "dashboard-a@example.edu")
        id_b = login(b, "dashboard-b@example.edu")
        login(admin, "dashboard-admin@example.edu")
        ticket_a = a.post("/api/tickets", json=ticket_payload("A dashboard record"), headers=csrf_headers(a)).json()
        ticket_b = b.post("/api/tickets", json=ticket_payload("B dashboard record"), headers=csrf_headers(b)).json()
        with test_db() as db:
            db.get(Ticket, ticket_a["id"]).status = TicketStatus.resolved
            db.get(Ticket, ticket_b["id"]).status = TicketStatus.in_progress
            historical = Ticket(
                id="HD-HIST0002", title="Historical dashboard ticket", description="Unlinked history.",
                category=TicketCategory.other, priority=TicketPriority.low, status=TicketStatus.open,
                owner="Old owner", user_id=None,
            )
            db.add(historical)
            db.flush()
            run_a = create_run(db, id_a, "A private dashboard workflow", ticket_a["id"])
            run_b = create_run(db, id_b, "B private dashboard workflow", ticket_b["id"])
            historical_run = create_run(db, None, "Unlinked historical workflow")

        data_a = a.get("/api/dashboard").json()
        data_b = b.get("/api/dashboard").json()
        all_data = admin.get("/api/dashboard").json()
        assert (data_a["open_tickets"], data_a["in_progress_tickets"], data_a["resolved_tickets"]) == (0, 0, 1)
        assert [row["id"] for row in data_a["recent_tickets"]] == [ticket_a["id"]]
        assert {row["workflow_id"] for row in data_a["ai_activity"]} == {run_a.id}
        assert (data_b["open_tickets"], data_b["in_progress_tickets"], data_b["resolved_tickets"]) == (0, 1, 0)
        assert {row["workflow_id"] for row in data_b["ai_activity"]} == {run_b.id}
        assert (all_data["open_tickets"], all_data["in_progress_tickets"], all_data["resolved_tickets"]) == (1, 1, 1)
        assert {row["workflow_id"] for row in all_data["ai_activity"]} == {run_a.id, run_b.id, historical_run.id}
        assert "HD-HIST0002" in {row["id"] for row in all_data["recent_tickets"]}


def test_chat_requires_auth_and_receives_no_other_users_private_records(test_db):
    create_account(test_db, "chat-a@example.edu")
    create_account(test_db, "chat-b@example.edu")
    with ExitStack() as stack:
        a, b = (stack.enter_context(TestClient(app)) for _ in range(2))
        id_a = login(a, "chat-a@example.edu")
        id_b = login(b, "chat-b@example.edu")
        private_ticket = b.post("/api/tickets", json=ticket_payload("B secret incident", description="B_SECRET_TICKET_DESCRIPTION"), headers=csrf_headers(b)).json()
        with test_db() as db:
            create_run(db, id_b, "B_SECRET_WORKFLOW_ISSUE", private_ticket["id"])

        captured = {}

        class FakeChat:
            def answer(self, issue):
                captured["issue"] = issue
                return SimpleNamespace(text="I can help with your reported issue.", sources=[])

        app.dependency_overrides[get_groq_service] = lambda: FakeChat()
        no_session = TestClient(app)
        token = no_session.get("/api/auth/csrf", headers={"Origin": ORIGIN}).json()["csrf_token"]
        unauthenticated = no_session.post(
            "/api/ai/chat",
            json={"issue": "I need help connecting to Wi-Fi"},
            headers={"Origin": ORIGIN, "X-CSRF-Token": token},
        )
        assert unauthenticated.status_code == 401

        response = a.post("/api/ai/chat", json={"issue": "I need help connecting to Wi-Fi"}, headers=csrf_headers(a))
        assert response.status_code == 200
        assert captured["issue"] == "I need help connecting to Wi-Fi"
        assert "B_SECRET" not in str(captured)
        assert private_ticket["id"] not in response.text
