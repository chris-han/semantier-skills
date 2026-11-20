"""Offline bilingual contract and evaluator tests; these do not call a model."""
import copy
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from bilingual_eval import (DATASET, LANGUAGES, load_pairs, make_messages,
                            route_tuple, score_condition, cross_locale_consistency,
                            script_heuristic, run)


class BilingualContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pairs = load_pairs(DATASET, 100)

    def test_frozen_language_triples(self):
        self.assertEqual(len(self.pairs), 24)
        self.assertEqual(len({p["id"] for p in self.pairs}), 24)
        for p in self.pairs:
            with self.subTest(p["id"]):
                self.assertEqual(set(p["requests"]), set(LANGUAGES))
                self.assertEqual(set(p["response_language"]), set(LANGUAGES))
                self.assertFalse(re.search(r"[\u3400-\u9fff]", p["requests"]["en"]))
                self.assertRegex(p["requests"]["zh"], r"[\u3400-\u9fff]")
                self.assertRegex(p["requests"]["mixed"], r"[\u3400-\u9fff]")
                self.assertRegex(p["requests"]["mixed"], r"[A-Za-z]")
                if p.get("preserve_quote"):
                    for locale in LANGUAGES:
                        self.assertIn(p["preserve_quote"], p["requests"][locale])

    def test_depth_tasks_modes_and_specialists(self):
        cases = self.pairs
        self.assertEqual({c["expected"]["depth"] for c in cases}, {"L0", "L1", "L2", "L3"})
        for lead in ("inquiry", "decision", "writing"):
            for depth in ("L1", "L2", "L3"):
                self.assertTrue(any(c["expected"]["lead"] == lead and c["expected"]["depth"] == depth
                                    for c in cases), f"missing {lead}/{depth}")
        self.assertEqual({c["expected"]["depth"] for c in cases if c["expected"]["mode"] == "coach"},
                         {"L1", "L2", "L3"})
        self.assertTrue(any(c["expected"]["specialists"] == ["ethical"] for c in cases))
        self.assertTrue(any(c["expected"]["specialists"] == ["organizational"] for c in cases))
        self.assertTrue(any(set(c["expected"]["specialists"]) == {"ethical", "organizational"} for c in cases))
        self.assertTrue(any(c["response_language"]["zh"] == "en" for c in cases))
        self.assertTrue(any(c["expected"]["ask_user"] for c in cases))
        self.assertTrue(any(c["expected"]["mode"] == "deliver" and not c["expected"]["ask_user"] for c in cases))
        self.assertTrue(all(c["expected"]["depth"] == "L0" and not c["expected"]["specialists"]
                            for c in cases if c["expected"]["lead"] == "none"))

    def test_dataset_smoke_is_not_model_success(self):
        report = run(DATASET, 24)
        self.assertEqual(report["selected_pairs"], 24)
        self.assertEqual(report["prompt_variants"], 72)
        self.assertEqual(report["model_calls_attempted"], 0)
        self.assertEqual(report["eval_type"], "ORACLE_SCHEMA_SMOKE_ONLY")
        self.assertNotIn("conditions", report)
        self.assertNotIn("delta_self_reported_route_accuracy", report)

    def test_model_messages_keep_user_prompt_equal_between_arms(self):
        case = self.pairs[3]
        base = make_messages(case, "zh", "baseline")
        skill = make_messages(case, "zh", "skill")
        self.assertEqual(base[-1]["content"], skill[-1]["content"])
        self.assertIn("Semantier Thinking", skill[0]["content"])
        self.assertNotIn("Semantier Thinking", base[0]["content"])
        self.assertIn("假设", skill[0]["content"])
        self.assertIn('"lead":"none|inquiry', base[1]["content"])
        self.assertNotIn(case["reason"], base[0]["content"] + base[-1]["content"])
        with self.assertRaises(ValueError):
            make_messages(case, "de", "skill")

    def test_language_contract_and_documentation(self):
        root = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        guidance = (ROOT / "references/language-and-terminology.md").read_text(encoding="utf-8")
        english = (ROOT / "README.md").read_text(encoding="utf-8")
        chinese = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        self.assertIn("Respond in the user's requested language", root)
        self.assertIn("Keep the same task, depth, mode", root)
        self.assertIn("quotation", guidance)
        self.assertIn("反证", guidance)
        self.assertIn("[简体中文说明 / Chinese README](README.zh-CN.md)", english)
        self.assertIn("[SKILL.md](SKILL.md)", chinese)
        self.assertIn("官方", chinese)
        self.assertIn("0.1.1", chinese)

    def test_script_heuristic_has_known_false_negatives(self):
        self.assertEqual(script_heuristic("这是一个需要补充证据的判断。"), "zh")
        self.assertEqual(script_heuristic("The evidence is limited."), "en")
        self.assertEqual(script_heuristic("否"), "en")

    def test_invalid_model_prediction_counts_as_failure(self):
        expected = self.pairs[3]["expected"]
        good = {**expected, "answer": "仅凭先后关系不足以证明因果。"}
        wrong = {**expected, "lead": "decision", "answer": "不能据此证明因果。"}
        rows = [{"prediction": obj, "expected": expected, "response_language": "zh"}
                for obj in (good, wrong, None)]
        score = score_condition(rows)
        self.assertEqual(score["total"], 3)
        self.assertEqual(score["valid"], 2)
        self.assertEqual(score["invalid"], 1)
        self.assertEqual(score["route_correct"], 1)
        self.assertEqual(score["route_accuracy_total"], 0.3333)

    def test_cross_language_consistency_does_not_drop_incomplete_cases(self):
        expected = self.pairs[3]["expected"]
        good = {**expected, "answer": "This is not proven."}
        wrong = {**expected, "depth": "L2", "answer": "可能仍有其他解释。"}
        rows = []
        for locale in LANGUAGES:
            rows.append({"case_id": "A", "locale": locale, "prediction": good})
        for locale in LANGUAGES:
            rows.append({"case_id": "B", "locale": locale, "prediction": wrong if locale == "zh" else good})
        for locale in LANGUAGES[:2]:
            rows.append({"case_id": "C", "locale": locale, "prediction": good})
        result = cross_locale_consistency(rows)
        self.assertEqual(result, {"triples": 3, "complete": 2,
                                  "consistent": 1, "consistency_rate_total": 0.3333})

    def test_verbatim_source_quote_metric(self):
        case = next(c for c in self.pairs if c.get("preserve_quote"))
        prediction = {**case["expected"],
                      "answer": "原文：" + case["preserve_quote"] + "。但观察性证据不足以证明因果。"}
        row = {"prediction": prediction, "expected": case["expected"], "response_language": "zh",
               "preserve_quote": case["preserve_quote"]}
        self.assertEqual(score_condition([row])["quote_preserved"], 1)
        prediction["answer"] = "原文已经译写，无法逐字核对。"
        self.assertEqual(score_condition([row])["quote_preserved"], 0)

    def test_invalid_fixture_rejected_before_driver(self):
        bad = copy.deepcopy(self.pairs[:1])
        del bad[0]["requests"]["mixed"]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "broken.json"
            path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_pairs(path, 1)
        with self.assertRaises(ValueError):
            load_pairs(DATASET, 0)
        with self.assertRaises(ValueError):
            load_pairs(DATASET, 101)

    def test_route_schema_rejects_unrecognized_model_labels(self):
        for case in self.pairs:
            with self.subTest(case["id"]):
                good = {**case["expected"], "answer": "基于证据的回答。"}
                self.assertIsNotNone(route_tuple(good))
                self.assertIsNone(route_tuple({**good, "mode": "unsupported"}))


if __name__ == "__main__":
    unittest.main()
