"""Deterministic source/package and evaluation-runner contract checks (no model)."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
EVAL = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL))
from folio_benchmark import parse_examples, make_messages, score, run


class SkillContractTests(unittest.TestCase):
    def test_source_identity_and_license(self):
        root = (BASE / "SKILL.md").read_text(encoding="utf-8")
        self.assertRegex(root, r"(?m)^name: semantier--semantier-thinking$")
        self.assertRegex(root, r'(?m)^version: "0\.1\.0"$')
        self.assertIn("Copyright (c) 2026 Semantier Technology", (BASE / "LICENSE").read_text())
        self.assertFalse((BASE / "plugin.yaml").exists(), "ordinary standalone skill must not masquerade as plugin")

    def test_all_disclosure_paths_resolve(self):
        files = [p for p in BASE.rglob("*.md") if p.is_file()]
        found = set()
        for file in files:
            for target in re.findall(r"\]\(([^)]+\.md)\)", file.read_text(encoding="utf-8")):
                linked = file.parent / target
                self.assertTrue(linked.is_file(), f"missing disclosure path {file}: {target}")
                found.add(linked.resolve())
        required = {BASE / "references" / f for f in ["depth-routing.md", "critical-inquiry.md", "decision-reasoning.md", "argument-writing.md", "ethical-reasoning.md", "organizational-reasoning.md", "evidence-handoff.md", "attribution-and-scope.md"]}
        self.assertTrue({f.resolve() for f in required}.issubset(found), "all task and specialist references must be linked")

    def test_depth_and_mode_are_independent(self):
        data = json.loads((EVAL / "scenarios.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data), 20)
        self.assertEqual(len({x["id"] for x in data}), len(data))
        self.assertEqual({x["depth"] for x in data}, {"L0", "L1", "L2", "L3"})
        self.assertEqual({x["mode"] for x in data}, {"deliver", "coach"})
        self.assertEqual({x["lead"] for x in data}, {"none", "inquiry", "decision", "writing"})
        self.assertTrue(any(x["depth"] == "L1" and x["mode"] == "coach" for x in data))
        self.assertTrue(any(x["depth"] == "L3" and x["mode"] == "deliver" for x in data))
        self.assertTrue(any(set(x["specialists"]) == {"ethical", "organizational"} for x in data))
        for x in data:
            with self.subTest(id=x["id"]):
                self.assertTrue(x["request"] and x["reason"])
                self.assertFalse(x["depth"] == "L0" and x["specialists"])
                self.assertFalse(x["lead"] == "none" and x["depth"] != "L0")
                self.assertLessEqual(len(x["specialists"]), 2)
                self.assertTrue(set(x["specialists"]).issubset({"ethical", "organizational"}))

    def test_progressive_and_security_gates_documented(self):
        body = "\n".join(p.read_text(encoding="utf-8") for p in (BASE / "SKILL.md", BASE / "references/depth-routing.md", BASE / "references/evidence-handoff.md", BASE / "references/attribution-and-scope.md"))
        for token in ["L0", "L1", "L2", "L3", "Coach", "Deliver", "source", "unknown", "semantier/semantier/semantier-thinking", "semantier--semantier-thinking", "signature", "STOP"]:
            with self.subTest(token=token):
                self.assertIn(token.lower(), body.lower())


class FOLIOAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dataset = Path(self.temp.name) / "folio-fixture.jsonl"
        self.dataset.write_text("\n".join(json.dumps(x) for x in [
            {"premises": ["All p are q.", "Ann is p."], "conclusion": "Ann is q.", "label": "True"},
            {"premises": ["No p are q.", "Ann is p."], "conclusion": "Ann is q.", "label": "False"},
            {"premises": ["All p are q.", "Ann is q."], "conclusion": "Ann is p.", "label": "Uncertain"}
        ]) + "\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_parser_bounded_and_three_labels(self):
        out = parse_examples(self.dataset, 3)
        self.assertEqual([x["label"] for x in out], ["True", "False", "Uncertain"])
        self.assertRaises(ValueError, parse_examples, self.dataset, 0)
        self.assertRaises(ValueError, parse_examples, self.dataset, 1001)

    def test_prompt_conditions_distinct_and_bound_to_premises(self):
        e = parse_examples(self.dataset, 1)[0]
        b = make_messages(e, "baseline")
        s = make_messages(e, "skill")
        self.assertIn("Premises:", b[1]["content"])
        self.assertIn("Ann is q.", b[1]["content"])
        self.assertNotIn("Semantier Thinking", b[0]["content"])
        self.assertIn("Semantier Thinking", s[0]["content"])
        self.assertIn("Do not use outside world knowledge", s[1]["content"])

    def test_gold_not_misreported_as_model_accuracy(self):
        output = run(self.dataset, 3)
        self.assertEqual(output["model_runs"], 0)
        self.assertEqual(output["eval_type"], "DATASET_SCHEMA_SMOKE_ONLY")
        self.assertEqual(output["gold_counts"], {"True": 1, "False": 1, "Uncertain": 1})
        self.assertNotIn("paired_delta_total_accuracy", output)

    def test_scorer_includes_invalid_predictions_in_denominator(self):
        report = score([{"prediction": "True", "gold": "True"}, {"prediction": "Uncertain", "gold": "False"}, {"prediction": None, "gold": "Uncertain"}])
        self.assertEqual(report, {"total": 3, "valid": 2, "invalid": 1, "correct": 1, "accuracy_total": 0.3333})

    def test_dataset_schema_failure_is_detected(self):
        self.dataset.write_text('{"premises":[],"conclusion":"A","label":"True"}\n', encoding="utf-8")
        with self.assertRaises(ValueError):
            parse_examples(self.dataset, 1)


if __name__ == "__main__":
    unittest.main()
