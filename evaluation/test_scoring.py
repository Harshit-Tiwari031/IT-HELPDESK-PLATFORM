"""Offline tests for evaluation metric calculations; no app or provider imports."""

import json
import unittest
from pathlib import Path

from score_results import EvaluationInputError, score_results


CASES = {
    "cases": [
        {"case_id": "network-01", "expected_decision": "resolve", "expected_tool": "simulated_network_connectivity"},
        {"case_id": "dns-01", "expected_decision": "resolve", "expected_tool": "simulated_dns_resolution"},
        {"case_id": "vague-01", "expected_decision": "escalate", "expected_tool": None},
        {"case_id": "unsupported-01", "expected_decision": "escalate", "expected_tool": None},
    ]
}


def result(case_id, decision, selected_tool=None, **extra):
    return {"case_id": case_id, "decision": decision, "selected_tool": selected_tool, **extra}


class ScoringTests(unittest.TestCase):
    def test_decision_accuracy_escalation_precision_recall_and_tool_selection(self):
        scored = score_results(CASES, {"run_id": "offline-test", "system_variant": "proposed", "results": [
            result("network-01", "resolve", "simulated_network_connectivity"),
            result("dns-01", "escalate"),
            result("vague-01", "escalate"),
            result("unsupported-01", "resolve"),
        ]})

        self.assertEqual(scored["decision_accuracy"], {"correct": 2, "denominator": 4, "value": 0.5})
        self.assertEqual(scored["escalation_precision"], {"true_positive": 1, "denominator": 2, "value": 0.5})
        self.assertEqual(scored["escalation_recall"], {"true_positive": 1, "denominator": 2, "value": 0.5})
        self.assertEqual(scored["correct_tool_selection"], {"applicable": True, "correct": 1, "denominator": 2, "value": 0.5})

    def test_human_intervention_rate_uses_completed_observed_decisions(self):
        scored = score_results(CASES, {"system_variant": "proposed", "results": [
            result("network-01", "escalate"),
            result("dns-01", "resolve", "simulated_dns_resolution"),
            result("vague-01", "escalate"),
        ]})

        self.assertEqual(scored["human_intervention_rate"], {"escalated": 2, "denominator": 3, "value": 0.6667})

    def test_missing_and_failed_results_are_reported_and_excluded_not_imputed(self):
        scored = score_results(CASES, {"system_variant": "proposed", "results": [
            result("network-01", "resolve", "simulated_network_connectivity"),
            {"case_id": "dns-01", "status": "provider_failure"},
        ]})

        self.assertEqual(scored["completed_count"], 1)
        self.assertEqual(scored["missing_count"], 3)
        self.assertEqual(scored["coverage"], 0.25)
        self.assertEqual(scored["decision_accuracy"]["value"], 1.0)
        self.assertEqual(scored["missing_cases"], [
            {"case_id": "dns-01", "reason": "provider_failure"},
            {"case_id": "unsupported-01", "reason": "not_supplied"},
            {"case_id": "vague-01", "reason": "not_supplied"},
        ])

    def test_zero_denominators_and_empty_outcomes_return_null_ratios(self):
        scored = score_results(CASES, {"system_variant": "proposed", "results": []})

        self.assertIsNone(scored["decision_accuracy"]["value"])
        self.assertIsNone(scored["escalation_precision"]["value"])
        self.assertIsNone(scored["escalation_recall"]["value"])
        self.assertTrue(scored["correct_tool_selection"]["applicable"])
        self.assertIsNone(scored["correct_tool_selection"]["value"])
        self.assertIsNone(scored["human_intervention_rate"]["value"])
        self.assertIsNone(scored["latency_seconds"]["mean"])
        self.assertIsNone(scored["latency_seconds"]["median"])

    def test_latency_and_out_of_allowlist_attempts_are_counted_from_inputs(self):
        scored = score_results(CASES, {"system_variant": "proposed", "results": [
            result("network-01", "resolve", "simulated_network_connectivity", tool_attempts=["simulated_network_connectivity", "run_shell_command"], latency_seconds=1.0),
            result("dns-01", "resolve", "simulated_dns_resolution", latency_seconds=3.0),
        ]})

        self.assertEqual(scored["out_of_allowlist_attempts"], {"attempt_count": 1, "case_count": 1})
        self.assertEqual(scored["latency_seconds"], {"observed_count": 2, "mean": 2.0, "median": 2.0})

    def test_duplicate_and_unknown_outcome_ids_are_rejected(self):
        duplicate = {"system_variant": "proposed", "results": [result("network-01", "resolve"), result("network-01", "resolve")]}
        unknown = {"system_variant": "proposed", "results": [result("unknown-case", "resolve")]}

        with self.assertRaisesRegex(EvaluationInputError, "Duplicate"):
            score_results(CASES, duplicate)
        with self.assertRaisesRegex(EvaluationInputError, "Unknown"):
            score_results(CASES, unknown)

    def test_paper_baseline_tool_selection_is_not_applicable(self):
        scored = score_results(CASES, {"system_variant": "baseline", "results": [
            result("network-01", "resolve"),
            result("dns-01", "escalate"),
        ]})

        self.assertFalse(scored["correct_tool_selection"]["applicable"])
        self.assertIsNone(scored["correct_tool_selection"]["value"])

    def test_synthetic_case_file_has_all_requested_scenario_types(self):
        case_file = Path(__file__).with_name("cases.json")
        with case_file.open(encoding="utf-8") as source:
            document = json.load(source)
        types = {case["scenario_type"] for case in document["cases"]}
        self.assertEqual(len(document["cases"]), 14)
        self.assertEqual(types, {
            "network_connectivity", "dns_resolution", "service_health", "account_access",
            "vague_request", "unsupported_request", "safety_bypass_attempt",
        })
        scored = score_results(document, {"system_variant": "proposed", "results": []})
        self.assertEqual(scored["missing_count"], 14)
        self.assertEqual(scored["decision_accuracy"]["value"], None)


if __name__ == "__main__":
    unittest.main()
