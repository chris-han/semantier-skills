from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
import json
import os
from pathlib import Path

class ObservationStore:
    """Small append-only store; production binding can replace this surface."""
    def __init__(self): self._observations: dict[str, dict] = {}; self._runs: dict[str, dict] = {}; self._checkpoints: dict[str, dict] = {}
    def append(self, observation: dict) -> dict:
        envelope = observation.get("github_observation", observation)
        ref = envelope["source_ref"]
        self._observations.setdefault(ref, observation)
        artifacts_root = os.environ.get("SEMANTIER_WORKSPACE_ARTIFACTS_DIR")
        if artifacts_root:
            path = Path(artifacts_root).resolve() / "vc_github_opportunity_radar" / "observations.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"source_ref": ref, "observation": observation}, sort_keys=True, default=str) + "\n")
        return self._observations[ref]
    def get(self, ref: str): return self._observations.get(ref)
    def list(self): return list(self._observations.values())
    def start_run(self, *, universe_ref: str, budget: int) -> dict:
        run = {"run_id": f"radar_run_{uuid4().hex}", "universe_ref": universe_ref, "budget": budget, "status": "RUNNING", "started_at": datetime.now(timezone.utc).isoformat(), "processed": 0, "errors": []}
        self._runs[run["run_id"]] = run
        return run
    def checkpoint(self, run_id: str, cursor: dict) -> None:
        self._checkpoints[run_id] = dict(cursor)
    def finish_run(self, run_id: str, *, status: str, processed: int, errors: list[str] | None = None) -> dict:
        run = self._runs[run_id]; run.update({"status": status, "processed": processed, "errors": errors or [], "finished_at": datetime.now(timezone.utc).isoformat()})
        artifacts_root = os.environ.get("SEMANTIER_WORKSPACE_ARTIFACTS_DIR")
        if artifacts_root:
            path = Path(artifacts_root).resolve() / "vc_github_opportunity_radar" / "scan-runs" / f"{run_id}.json"
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps({"run": run, "checkpoint": self._checkpoints.get(run_id)}, sort_keys=True), encoding="utf-8")
        return dict(run)
    def get_run(self, run_id: str) -> dict | None: return self._runs.get(run_id)
    def get_checkpoint(self, run_id: str) -> dict | None: return self._checkpoints.get(run_id)
