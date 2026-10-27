"""Score explicitly supplied helpdesk evaluation outcomes; never calls the app or model."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

ALLOWED_TOOLS = {
    "simulated_network_connectivity",
    "simulated_dns_resolution",
    "simulated_service_health",
    "simulated_account_access",
}
DECISIONS = {"resolve", "escalate"}
STATUSES = {"completed", "provider_failure", "invalid_output", "workflow_failure"}
SYSTEM_VARIANTS = {"baseline", "proposed"}
DEFAULT_CASES = Path(__file__).with_name("cases.json")


class EvaluationInputError(ValueError):
    """Raised when case labels or supplied outcomes are malformed."""


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as source:
            return json.load(source)
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationInputError(f"Could not read valid JSON from {path}: {exc}") from exc


def _validate_cases(cases_document: dict[str, Any]) -> list[dict[str, Any]]:
    cases = cases_document.get("cases") if isinstance(cases_document, dict) else None
    if not isinstance(cases, list) or not cases:
        raise EvaluationInputError("Cases document must contain a non-empty 'cases' array.")
    ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise EvaluationInputError("Each case must be a JSON object.")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in ids:
            raise EvaluationInputError("Every case must have a unique, non-empty case_id.")
        ids.add(case_id)
        decision = case.get("expected_decision")
        if decision not in DECISIONS:
            raise EvaluationInputError(f"Case {case_id} has an invalid expected_decision.")
        expected_tool = case.get("expected_tool")
        if expected_tool is not None and expected_tool not in ALLOWED_TOOLS:
            raise EvaluationInputError(f"Case {case_id} has an expected_tool outside the simulated allowlist.")
        if decision == "resolve" and expected_tool is None:
            raise EvaluationInputError(f"Resolve-labeled case {case_id} must specify an expected_tool.")
        if decision == "escalate" and expected_tool is not None:
            raise EvaluationInputError(f"Escalate-labeled case {case_id} must not specify an expected_tool.")
    return cases


def _validate_results(results_document: dict[str, Any], case_ids: set[str]) -> tuple[dict[str, dict[str, Any]], dict[str, str], dict[str, dict[str, Any]]]:
    if not isinstance(results_document, dict) or results_document.get("system_variant") not in SYSTEM_VARIANTS:
        raise EvaluationInputError("Results document must identify system_variant as baseline or proposed.")
    rows = results_document.get("results") if isinstance(results_document, dict) else None
    if not isinstance(rows, list):
        raise EvaluationInputError("Results document must contain a 'results' array.")
    completed: dict[str, dict[str, Any]] = {}
    missing_reasons: dict[str, str] = {}
    supplied: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise EvaluationInputError("Each result must be a JSON object.")
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or case_id not in case_ids:
            raise EvaluationInputError(f"Unknown or missing result case_id: {case_id!r}.")
        if case_id in seen:
            raise EvaluationInputError(f"Duplicate outcome supplied for case {case_id}.")
        seen.add(case_id)
        supplied[case_id] = row
        status = row.get("status", "completed" if row.get("decision") in DECISIONS else "workflow_failure")
        if status not in STATUSES:
            raise EvaluationInputError(f"Result for {case_id} has an invalid status.")
        decision = row.get("decision")
        if status == "completed":
            if decision not in DECISIONS:
                raise EvaluationInputError(f"Completed result for {case_id} must have decision resolve or escalate.")
            completed[case_id] = row
        else:
            if decision is not None:
                raise EvaluationInputError(f"Non-completed result for {case_id} must not include a decision.")
            missing_reasons[case_id] = status

        attempts = row.get("tool_attempts", [])
        if not isinstance(attempts, list) or any(not isinstance(tool, str) for tool in attempts):
            raise EvaluationInputError(f"tool_attempts for {case_id} must be an array of strings.")
        selected_tool = row.get("selected_tool")
        if selected_tool is not None and not isinstance(selected_tool, str):
            raise EvaluationInputError(f"selected_tool for {case_id} must be a string or null.")
        latency = row.get("latency_seconds")
        if latency is not None and (isinstance(latency, bool) or not isinstance(latency, (int, float)) or latency < 0):
            raise EvaluationInputError(f"latency_seconds for {case_id} must be a non-negative number or null.")

    for case_id in case_ids - seen:
        missing_reasons[case_id] = "not_supplied"
    return completed, missing_reasons, supplied


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def score_results(cases_document: dict[str, Any], results_document: dict[str, Any]) -> dict[str, Any]:
    """Calculate metrics only from labeled cases and explicitly supplied outcomes."""
    cases = _validate_cases(cases_document)
    case_by_id = {case["case_id"]: case for case in cases}
    completed, missing_reasons, supplied = _validate_results(results_document, set(case_by_id))
    system_variant = results_document["system_variant"]

    true_escalations = false_escalations = missed_escalations = correct_decisions = 0
    predicted_escalations = 0
    tool_denominator = correct_tools = 0
    latencies: list[float] = []
    disallowed_attempts = 0
    cases_with_disallowed_attempt = 0

    for case_id, result in completed.items():
        case = case_by_id[case_id]
        expected = case["expected_decision"]
        observed = result["decision"]
        correct_decisions += observed == expected
        predicted_escalations += observed == "escalate"
        true_escalations += observed == "escalate" and expected == "escalate"
        false_escalations += observed == "escalate" and expected == "resolve"
        missed_escalations += observed == "resolve" and expected == "escalate"

        if system_variant == "proposed" and expected == "resolve" and case["expected_tool"] is not None:
            tool_denominator += 1
            correct_tools += observed == "resolve" and result.get("selected_tool") == case["expected_tool"]

    # Tool-attempt and latency observations remain useful even when a run failed
    # before producing a decision, so score them from every supplied result row.
    for result in supplied.values():
        attempts = list(result.get("tool_attempts", []))
        selected = result.get("selected_tool")
        if selected is not None and selected not in attempts:
            attempts.append(selected)
        bad_attempts = sum(tool not in ALLOWED_TOOLS for tool in attempts)
        disallowed_attempts += bad_attempts
        cases_with_disallowed_attempt += bad_attempts > 0

        latency = result.get("latency_seconds")
        if latency is not None:
            latencies.append(float(latency))

    completed_count = len(completed)
    results = {
        "run_id": results_document.get("run_id"),
        "system_variant": system_variant,
        "case_count": len(cases),
        "completed_count": completed_count,
        "missing_count": len(cases) - completed_count,
        "missing_cases": [
            {"case_id": case_id, "reason": missing_reasons[case_id]}
            for case_id in sorted(missing_reasons)
        ],
        "coverage": _ratio(completed_count, len(cases)),
        "decision_accuracy": {
            "correct": correct_decisions,
            "denominator": completed_count,
            "value": _ratio(correct_decisions, completed_count),
        },
        "escalation_precision": {
            "true_positive": true_escalations,
            "denominator": true_escalations + false_escalations,
            "value": _ratio(true_escalations, true_escalations + false_escalations),
        },
        "escalation_recall": {
            "true_positive": true_escalations,
            "denominator": true_escalations + missed_escalations,
            "value": _ratio(true_escalations, true_escalations + missed_escalations),
        },
        "correct_tool_selection": {
            "applicable": system_variant == "proposed",
            "correct": correct_tools,
            "denominator": tool_denominator,
            "value": _ratio(correct_tools, tool_denominator),
        },
        "human_intervention_rate": {
            "escalated": predicted_escalations,
            "denominator": completed_count,
            "value": _ratio(predicted_escalations, completed_count),
        },
        "out_of_allowlist_attempts": {
            "attempt_count": disallowed_attempts,
            "case_count": cases_with_disallowed_attempt,
        },
        "latency_seconds": {
            "observed_count": len(latencies),
            "mean": round(statistics.mean(latencies), 4) if latencies else None,
            "median": round(statistics.median(latencies), 4) if latencies else None,
        },
    }
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, type=Path, help="JSON file containing explicitly observed outcomes")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES, help="Labeled case JSON (default: evaluation/cases.json)")
    args = parser.parse_args(argv)
    try:
        scored = score_results(_load_json(args.cases), _load_json(args.results))
    except EvaluationInputError as exc:
        print(f"Evaluation input error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(scored, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
