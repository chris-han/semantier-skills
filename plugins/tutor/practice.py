"""Deterministic pedagogy for a frozen, source-grounded choice exercise."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class ChoiceExercise:
    stem: str
    options: tuple[tuple[str, str], ...]
    key: str
    rationale: str
    evidence_entries: tuple[str, ...]

    def __post_init__(self):
        if not self.stem.strip() or not self.rationale.strip():
            raise ValueError("question and rubric rationale required")
        if not isinstance(self.evidence_entries, tuple) or not self.evidence_entries:
            raise ValueError("source evidence entries required")
        if any(not isinstance(ref, str) or not ref.strip() for ref in self.evidence_entries):
            raise ValueError("empty evidence entry")
        if not isinstance(self.options, tuple) or not 2 <= len(self.options) <= 26:
            raise ValueError("expected two to twenty-six options")
        if any(not isinstance(pair, tuple) or len(pair) != 2 for pair in self.options):
            raise ValueError("expected immutable option pairs")
        labels = {label for label, _ in self.options}
        expected = {chr(ord("A") + index) for index in range(len(self.options))}
        if labels != expected or self.key not in labels:
            raise ValueError("invalid choice labels or key")
        bodies = {body.strip().casefold() for _, body in self.options}
        if "" in bodies or len(bodies) != len(labels) or bodies & {label.lower() for label in labels}:
            raise ValueError("ambiguous choice text")

    def learner_view(self):
        return {"question": self.stem, "options": dict(self.options)}

    def grade(self, answer: str) -> str:
        candidate = answer.strip().casefold()
        for label, body in self.options:
            if candidate in (label.casefold(), body.strip().casefold()):
                return "correct" if label == self.key else "incorrect"
        return "ungraded"


_REVIEW_DAYS = {
    "memory": (0, 1, 3, 7, 14, 30, 60),
    "concept": (3, 7, 14, 30),
    "procedure": (3, 7, 14),
    "design": (14, 28),
}


def next_review(at: datetime, knowledge_type: str, review_round: int) -> datetime:
    """Compute a UTC recommendation from an explicit assessment time and round."""
    if at.utcoffset() is None or type(review_round) is not int or review_round < 0:
        raise ValueError("expected aware assessment time and nonnegative review round")
    intervals = _REVIEW_DAYS.get(knowledge_type)
    if intervals is None:
        raise ValueError("unsupported knowledge type")
    days = intervals[min(review_round, len(intervals) - 1)]
    return at.astimezone(timezone.utc) + timedelta(days=days)
