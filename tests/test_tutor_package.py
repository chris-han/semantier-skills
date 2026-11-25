import json
import unittest
from pathlib import Path

from plugins.tutor import register
from plugins.tutor.practice import ChoiceExercise


class PackageTests(unittest.TestCase):
    def test_registration_and_progress(self):
        tools = {}
        skills = {}

        class Context:
            def register_tool(self, **tool):
                tools[tool["name"]] = tool

            def register_skill(self, **skill):
                skills[skill["name"]] = skill

            def call_mcp(self, server, operation, args):
                assert (server, operation) == ("semantier_tutor", "tutor_progress")
                return {"ok": True, "structuredContent": {"objectives": [
                    {"status": "current", "knowledge_type": "concept", "assessments": [
                        {"result": "correct", "assistance": "independent", "assessment": "assessment:1", "submitted_at": "2026-11-25T12:00:00+00:00"},
                        {"result": "correct", "assistance": "hinted", "assessment": "assessment:2"},
                    ]},
                    {"status": "evidence_unavailable", "assessments": []},
                ]}}

        register(Context())
        self.assertEqual(set(tools), {"tutor_plan", "tutor_teach", "tutor_practice", "tutor_submit", "tutor_progress"})
        skill = Path(skills["tutor"]["path"])
        for language in ("en", "zh"):
            path = f"prompts/teaching.{language}.md"
            self.assertIn(path, skill.read_text())
            self.assertTrue((skill.parent / path).is_file())
        def core(operation, args, *, teach):
            self.assertEqual(operation, "tutor_teach")
            return teach(language="zh-CN", objective="观察", question="为什么？", passages={"E1": "一段材料"})

        response = tools["tutor_teach"]["handler"]({}, tutor_core=core)
        system, user = json.loads(response)["structuredContent"]
        self.assertEqual(system["content"], (skill.parent / "prompts/teaching.zh.md").read_text())
        self.assertEqual(json.loads(user["content"])["passages"], {"E1": "一段材料"})
        result = json.loads(tools["tutor_progress"]["handler"]({"project_ref": "p", "plan_ref": "l"}))
        current, unavailable = [item["mastery"] for item in result["objectives"]]
        self.assertEqual(current["estimate"], 0.5)
        self.assertEqual(current["next_review_at"], "2026-11-28T12:00:00+00:00")
        self.assertEqual(current["contributing_assessments"], ["assessment:1"])
        self.assertIsNone(unavailable["estimate"])

    def test_citation_must_support_the_frozen_key(self):
        from plugins.tutor.tools import grade_frozen_choice

        source = {"evidence": {"artifact_ref": "entry:1"},
                  "locator": {"selector": {"exact_quote": "The note records an observation."}}}
        exercise = {"question": "Complete the passage.\nThe note records an ____.",
                    "choices": [("A", "observation"), ("B", "inference")],
                    "rubric": {"key": "B", "rationale": "See the passage", "sources": [source]}}
        self.assertEqual(grade_frozen_choice(exercise, "B")["result"], "ungraded")
        exercise["rubric"]["key"] = "A"
        self.assertEqual(grade_frozen_choice(exercise, "A")["result"], "correct")
        source["locator"]["selector"]["exact_quote"] += " The note records an inference."
        self.assertEqual(grade_frozen_choice(exercise, "A")["result"], "ungraded")

    def test_immutable_choice_mapping(self):
        exercise = ChoiceExercise("Which?", (("B", "Prime"), ("A", "Composite")), "B", "Two divisors", ("entry:1",))
        self.assertEqual(exercise.grade("prime"), "correct")
        self.assertEqual(exercise.grade("A or B"), "ungraded")
        self.assertNotIn("key", exercise.learner_view())
