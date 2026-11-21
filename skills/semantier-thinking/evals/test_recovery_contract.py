"""Contract-level recovery scenarios for Semantier Thinking v0.1.2.

These tests inspect routing/transition instructions and the scenario oracle.
They do NOT claim actual model or native Hermes skill activation.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent


class RecoveryContractTests(unittest.TestCase):
    def test_reentry_is_conditional_and_not_generic_debugging(self):
        root = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        description = root.split("---", 2)[1]
        self.assertIn("materially challenges", description)
        self.assertIn("routine debugging", description)
        self.assertIn("reconsider", root.lower())
        self.assertIn("diagnostic-revision.md", root)

    def test_recovery_reference_has_distinct_evidence_and_handoff_stages(self):
        ref = (ROOT / "references/diagnostic-revision.md").read_text(encoding="utf-8")
        for phrase in [
            "observation", "competing explanations", "one discriminating",
            "specialist", "return", "source", "preserve", "STOP",
            "semantic UNKNOWN", "structural UNKNOWN", "meta-learning",
            "human", "exposed",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase.lower(), ref.lower())

    def test_compact_causality_and_provenance_rules(self):
        critical = (ROOT / "references/critical-inquiry.md").read_text(encoding="utf-8")
        handoff = (ROOT / "references/evidence-handoff.md").read_text(encoding="utf-8")
        self.assertIn("candidate", critical)
        self.assertIn("broader method", critical)
        self.assertIn("return observation", handoff)
        self.assertIn("unchanged", handoff)
        self.assertIn("conditional assessment", (ROOT / "references/diagnostic-revision.md").read_text(encoding="utf-8"))
        self.assertIn("independently verified", (ROOT / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("retrospective", handoff)

    def test_recovery_scenarios_are_bounded_and_distinguish_neighbors(self):
        cases = json.loads((HERE / "recovery_scenarios.json").read_text(encoding="utf-8"))
        self.assertEqual(len(cases), 8)
        ids = {c["id"] for c in cases}
        self.assertEqual(len(ids), len(cases))
        self.assertEqual({c["state"] for c in cases}, {
            "disputed_inference", "candidate_vs_method", "binding_defect",
            "residual_branch", "wrong_reason", "semantic_unknown",
            "settled_debugging", "valid_stop"
        })
        for c in cases:
            with self.subTest(c["id"]):
                self.assertTrue(c["user_turn"])
                self.assertTrue(c["expected_action"])
                self.assertIn(c["activate"], [True, False])
                self.assertIn(c["expected_claim"], ["bounded", "stop", "no_reentry"])
        self.assertGreaterEqual(sum(c["activate"] for c in cases), 4)
        self.assertGreaterEqual(sum(not c["activate"] for c in cases), 2)


if __name__ == "__main__":
    unittest.main()
