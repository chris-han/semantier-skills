from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return text or "resume-screening"


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_payload(payload: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def workspace_runs_dir() -> Path:
    raw = os.environ.get("SEMANTIER_WORKSPACE_RUNS_DIR")
    if not raw:
        try:
            from runtime_paths import current_workspace_runs_dir

            raw = current_workspace_runs_dir()
        except Exception:
            raw = None
    if not raw:
        raise RuntimeError("WORKSPACE_RUNS_DIR_REQUIRED: SEMANTIER_WORKSPACE_RUNS_DIR is required")
    return Path(raw).expanduser()


def write_screening_artifact(run_label: str, payload: dict[str, Any]) -> Path:
    run_root = workspace_runs_dir() / "auto_resume_screening" / _slug(run_label)
    run_root.mkdir(parents=True, exist_ok=True)
    artifact = dict(payload)
    artifact["created_at"] = utc_now_iso()
    artifact["content_hash"] = _hash_payload(artifact)
    path = run_root / "screening_result.json"
    path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path
