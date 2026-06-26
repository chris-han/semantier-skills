from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _error(error_code: str, message: str | None = None, **extra: Any) -> str:
    payload: dict[str, Any] = {"status": "error", "error_code": error_code}
    if message:
        payload["message"] = message
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


def _candidate_id_from_name(candidate_name: str, index: int) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", candidate_name.strip().lower()).strip("_")
    return normalized or f"candidate_{index}"


def extract_resume_text(args: dict[str, Any], **_kw: Any) -> str:
    from .extraction import extract_text_json

    resume_path = str(args.get("resume_path") or "").strip()
    if not resume_path:
        return _error("RESUME_PATH_REQUIRED", "resume_path is required")
    return extract_text_json(resume_path)


def rank_resume_candidates(args: dict[str, Any], **_kw: Any) -> str:
    from .scoring import rank_resumes

    job_profile = args.get("job_profile")
    resumes = args.get("resumes")
    if not isinstance(job_profile, dict):
        return _error("JOB_PROFILE_REQUIRED")
    if not isinstance(resumes, list):
        return _error("RESUMES_REQUIRED")
    return json.dumps(rank_resumes(job_profile, resumes), ensure_ascii=False)


def list_session_uploads(args: dict[str, Any] | None = None, **_kw: Any) -> str:
    from .extraction import list_session_upload_records

    return json.dumps(list_session_upload_records(), ensure_ascii=False)


def resolve_uploaded_resume(args: dict[str, Any], **_kw: Any) -> str:
    from .extraction import resolve_uploaded_resume_path

    query = str(args.get("query") or args.get("resume_path") or "").strip()
    return json.dumps(resolve_uploaded_resume_path(query), ensure_ascii=False)


def screen_resumes(args: dict[str, Any], **_kw: Any) -> str:
    from .artifacts import write_screening_artifact
    from .extraction import extract_text_from_resume, resolve_uploaded_resume_path
    from .scoring import rank_resumes

    job_profile = args.get("job_profile")
    resume_paths = args.get("resume_paths")
    run_label = str(args.get("run_label") or "resume-screening")
    if not isinstance(job_profile, dict):
        return _error("JOB_PROFILE_REQUIRED")
    if not isinstance(resume_paths, list) or not resume_paths:
        return _error("RESUME_PATHS_REQUIRED")

    extracted: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, raw_path in enumerate(resume_paths, start=1):
        resolved = resolve_uploaded_resume_path(str(raw_path))
        if resolved.get("status") == "ok":
            resume_path = Path(str(resolved["source_path"]))
        elif resolved.get("error_code") in {
            "SESSION_UPLOADS_CONTEXT_REQUIRED",
            "NO_SUPPORTED_UPLOADS",
            "UPLOAD_NOT_FOUND",
        }:
            resume_path = Path(str(raw_path))
        else:
            errors.append(resolved)
            continue

        result = extract_text_from_resume(resume_path)
        if result.get("status") != "ok":
            errors.append(result)
            continue
        source_path = str(result["source_path"])
        candidate_name = str(result.get("candidate_name") or "").strip()
        candidate_id = _candidate_id_from_name(candidate_name, index)
        extracted.append(
            {
                "candidate_id": candidate_id,
                "display_name_zh": candidate_name or candidate_id,
                "source_path": source_path,
                "text": str(result["text"]),
                "text_sha256": str(result["text_sha256"]),
            }
        )

    if not extracted:
        return _error("NO_RESUMES_EXTRACTED", errors=errors)

    ranking = rank_resumes(job_profile, extracted)
    payload = {
        "status": "ok",
        "job_profile": job_profile,
        "extracted": [{key: value for key, value in item.items() if key != "text"} for item in extracted],
        "errors": errors,
        "rankings": ranking["rankings"],
    }
    try:
        artifact_path = write_screening_artifact(run_label, payload)
    except RuntimeError as exc:
        code = str(exc).split(":", 1)[0]
        return _error(code, str(exc))

    response = dict(payload)
    response["artifact_path"] = str(artifact_path)
    return json.dumps(response, ensure_ascii=False)


def extract_role_terms(args: dict[str, Any], **_kw: Any) -> str:
    from .role_terms import extract_missing_role_terms

    source_urls = args.get("source_urls")
    if source_urls is not None and not isinstance(source_urls, list):
        return _error("SOURCE_URLS_INVALID", "source_urls must be an array of URLs")
    timeout_seconds = float(args.get("timeout_seconds") or 15)
    max_terms_per_source = int(args.get("max_terms_per_source") or 200)
    if timeout_seconds <= 0:
        return _error("TIMEOUT_SECONDS_INVALID", "timeout_seconds must be positive")
    if max_terms_per_source <= 0:
        return _error("MAX_TERMS_PER_SOURCE_INVALID", "max_terms_per_source must be positive")

    result = extract_missing_role_terms(
        [str(url) for url in source_urls] if source_urls is not None else None,
        timeout_seconds=timeout_seconds,
        max_terms_per_source=max_terms_per_source,
    )
    return json.dumps(result, ensure_ascii=False)
