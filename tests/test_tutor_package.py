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
                    {"status": "current", "assessments": [
                        {"result": "correct", "assistance": "independent", "assessment": "assessment:1"},
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
        result = json.loads(tools["tutor_progress"]["handler"]({"project_ref": "p", "plan_ref": "l"}))
        current, unavailable = [item["mastery"] for item in result["objectives"]]
        self.assertEqual(current["estimate"], 0.5)
        self.assertEqual(current["contributing_assessments"], ["assessment:1"])
        self.assertIsNone(unavailable["estimate"])

    def test_immutable_choice_mapping(self):
        exercise = ChoiceExercise("Which?", (("B", "Prime"), ("A", "Composite")), "B", "Two divisors", ("entry:1",))
        self.assertEqual(exercise.grade("prime"), "correct")
        self.assertEqual(exercise.grade("A or B"), "ungraded")
        self.assertNotIn("key", exercise.learner_view())
