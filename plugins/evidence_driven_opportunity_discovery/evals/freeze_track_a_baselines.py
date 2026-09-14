from __future__ import annotations

from pathlib import Path

from .runner import EvalRunPins, run_track_a, write_report


def main() -> None:
    root = Path(__file__).resolve().parent
    cases = root / "track_a_gold" / "cases.json"
    output = root / "baselines"
    for baseline in ("B0_random_seed0", "B1_keyword_heuristic"):
        report = run_track_a(
            cases_path=cases,
            pins=EvalRunPins(
                baseline=baseline,
                model="deterministic",
                runtime="python",
                tool_budget="none",
                prompt_or_skill_hash="none",
            ),
        )
        write_report(report, output / f"track_a_{baseline}.json")


if __name__ == "__main__":
    main()
