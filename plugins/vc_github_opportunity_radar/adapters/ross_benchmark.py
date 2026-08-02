from __future__ import annotations

from pathlib import Path
import json


class RossBenchmark:
    """Pinned offline cohort; no network access is permitted on the score path."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else Path(__file__).with_name("ross_benchmark_v1.json")
        self._data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"version": "ross_benchmark_v1", "capture_date": None, "cohort": []}

    @property
    def version(self) -> str: return str(self._data.get("version", "ross_benchmark_v1"))
    @property
    def capture_date(self) -> str | None: return self._data.get("capture_date")
    def normalize(self, value: float, field: str) -> float | None:
        values = [float(row[field]) for row in self._data.get("cohort", []) if row.get(field) is not None]
        if not values: return None
        return sum(item <= value for item in values) / len(values)
