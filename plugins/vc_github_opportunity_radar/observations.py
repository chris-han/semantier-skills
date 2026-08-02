from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

ADAPTER_VERSION = "github_rest_v1"

def utc(value: Any) -> str | None:
    if value in (None, ""): return None
    if isinstance(value, datetime): dt = value
    else: dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()

def normalize_repository(raw: dict[str, Any], *, observed_at: str | None = None) -> dict[str, Any]:
    repo = {
        "node_id": str(raw.get("node_id") or raw.get("id") or ""),
        "owner_login": str((raw.get("owner") or {}).get("login") or ""),
        "name": str(raw.get("name") or ""), "visibility": "public",
        "created_at": utc(raw.get("created_at")), "updated_at": utc(raw.get("updated_at")),
        "pushed_at": utc(raw.get("pushed_at")), "archived": bool(raw.get("archived", False)),
        "fork": bool(raw.get("fork", False)), "license_spdx": (raw.get("license") or {}).get("spdx_id"),
        "primary_language": raw.get("language"), "topics": sorted(str(x) for x in raw.get("topics", []) or []),
    }
    counters = {key: int(raw.get(key) or 0) for key in ("stargazers_count", "forks_count", "watchers_count", "open_issues_count")}
    counters = {"stars": counters["stargazers_count"], "forks": counters["forks_count"], "watchers": counters["watchers_count"], "open_issues": counters["open_issues_count"]}
    history = [
        {"observed_at": utc(item.get("observed_at")), "stars": int(item.get("stars"))}
        for item in raw.get("stars_history", []) or []
        if item.get("observed_at") not in (None, "") and item.get("stars") is not None
    ]
    selected = {"repository": repo, "counters": counters}
    response_hash = "sha256:" + hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest()
    selected_hash = "sha256:" + hashlib.sha256(json.dumps(selected, sort_keys=True).encode()).hexdigest()
    return {"github_observation": {"observation_id": selected_hash[7:23], "source": "github", "source_ref": f"github:repo:{repo['owner_login']}/{repo['name']}", "observed_at": utc(observed_at) or datetime.now(timezone.utc).isoformat(), "fetched_with": {"adapter_version": ADAPTER_VERSION, "api_mode": "rest"}, "repository": repo, "counters": counters, "history": history, "sampled_activity": {"commits": None, "distinct_commit_authors": None, "merged_pull_requests": None, "releases": None, "issue_participants": None}, "provenance": {"response_hash": response_hash, "selected_field_hash": selected_hash, "missing_fields": []}}}
