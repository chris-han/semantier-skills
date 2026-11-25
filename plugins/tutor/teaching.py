"""Build a teaching turn from this installed package and the host-selected passages."""
import json
from pathlib import Path


def teaching_turn(*, language, objective, passages, question=None):
    locale = "zh" if language.lower().split("-")[0] == "zh" else "en"
    asset = Path(__file__).with_name("prompts") / f"teaching.{locale}.md"
    return [
        {"role": "system", "content": asset.read_text(encoding="utf-8")},
        {"role": "user", "content": json.dumps({
            "language": language, "objective": objective, "question": question, "passages": passages,
        }, ensure_ascii=False)},
    ]
