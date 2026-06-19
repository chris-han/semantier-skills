from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _error(error_code: str, message: str | None = None, **extra: Any) -> str:
    payload: dict[str, Any] = {"status": "error", "error_code": error_code}
    if message:
        payload["message"] = message
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


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


def screen_resumes(args: dict[str, Any], **_kw: Any) -> str:
    from .artifacts import write_screening_artifact
    from .extraction import extract_text_from_resume
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
        result = extract_text_from_resume(Path(str(raw_path)))
        if result.get("status") != "ok":
            errors.append(result)
            continue
        source_path = str(result["source_path"])
        candidate_id = Path(source_path).stem or f"candidate_{index}"
        extracted.append(
            {
                "candidate_id": candidate_id,
                "display_name_zh": candidate_id,
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
