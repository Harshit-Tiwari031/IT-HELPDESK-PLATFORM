"""Offline tests for evaluation metric calculations; no app or provider imports."""

import json
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from score_results import EvaluationInputError, score_results
from run_pilot import (
    build_baseline_messages,
    main as pilot_main,
    normalize_generation_kwargs,
    planned_request_count,
    proposed_decision,
    safe_failure_record,
)


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

    def test_pilot_preflight_makes_no_provider_call_and_plans_28_requests(self):
        output = StringIO()
        with patch("sys.stdout", output):
            exit_code = pilot_main([])

        self.assertEqual(exit_code, 0)
        self.assertIn("28 Groq requests", output.getvalue())
        self.assertIn("no key or database was accessed", output.getvalue())

    def test_baseline_prompt_uses_articles_without_tools_or_decision_logic(self):
        article = type("Article", (), {
            "title": "Connect to verified Wi-Fi",
            "category": "Network",
            "steps": ("Check the network connection.",),
        })()
        messages = build_baseline_messages("Wi-Fi disconnects", [article])
        full_prompt = " ".join(message["content"] for message in messages).casefold()

        self.assertIn("connect to verified wi-fi", full_prompt)
        self.assertIn("check the network connection", full_prompt)
        self.assertIn("do not classify the issue into a resolution-versus-human-handoff outcome", full_prompt)
        self.assertNotIn("recommend escalation", full_prompt)
        self.assertNotIn("simulated_network_connectivity", full_prompt)

    def test_both_variants_share_sampling_parameters(self):
        normalized = normalize_generation_kwargs({
            "model": "test-model",
            "temperature": 0.2,
            "max_completion_tokens": 1800,
            "response_format": {"type": "json_object"},
        })

        self.assertEqual(normalized["temperature"], 0.1)
        self.assertEqual(normalized["max_completion_tokens"], 1200)
        self.assertEqual(normalized["response_format"], {"type": "json_object"})
        self.assertEqual(planned_request_count(14), 28)

    def test_proposed_mapping_is_only_a_recommendation_not_user_confirmation(self):
        self.assertEqual(proposed_decision("awaiting_user"), "resolve")
        self.assertEqual(proposed_decision("needs_escalation"), "escalate")
        with self.assertRaises(ValueError):
            proposed_decision("user_confirmed_resolved")

    def test_failure_record_does_not_expose_exception_text(self):
        class ProviderFailure(Exception):
            code = "GROQ_RATE_LIMITED"

        record = safe_failure_record(ProviderFailure("private response and secret"))
        self.assertEqual(record, {"status": "provider_failure", "error_code": "GROQ_RATE_LIMITED"})
        self.assertNotIn("private", json.dumps(record))

if __name__ == "__main__":
    unittest.main()
