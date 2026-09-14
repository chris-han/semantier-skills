from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from .live_preflight import inspect_hermes_provider_status


def _run(command: list[str], *, cwd: Path) -> int:
    completed = subprocess.run(command, cwd=cwd)
    return completed.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="Resume EOD live B2/B3 validation when a Hermes provider is ready.")
    parser.add_argument("--provider", default=None, help="Optional provider override recorded for the live runner.")
    parser.add_argument("--model", default=None, help="Optional model override recorded for the live runner.")
    parser.add_argument("--execute", action="store_true", help="Execute the live matrix after preflight instead of printing the next command.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[4]
    eval_root = Path(__file__).resolve().parent
    preflight = inspect_hermes_provider_status(repo_root)
    print(json.dumps(preflight, indent=2, sort_keys=True))
    if preflight["status"] != "READY":
        raise SystemExit(2)

    runner = eval_root / "run_live_b2_b3.py"
    command = [
        "uv",
        "run",
        "--extra",
        "dev",
        "python",
        str(runner),
        "--repeats",
        "3",
        "--output-dir",
        str(eval_root / "live_runs"),
    ]
    if args.provider:
        command += ["--provider", args.provider]
    if args.model:
        command += ["--model", args.model]

    if not runner.exists():
        print(json.dumps({
            "status": "READY_BUT_LIVE_RUNNER_MISSING",
            "expected_runner": str(runner),
            "next_command": command,
        }, indent=2))
        raise SystemExit(3)

    if not args.execute:
        print(json.dumps({"status": "READY", "next_command": command}, indent=2))
        return

    raise SystemExit(_run(command, cwd=repo_root))


if __name__ == "__main__":
    main()
