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
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", candidate_name.strip().lower()).strip(
        "_"
    )
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

    if args.get("mode") == "lineage_v1":
        return _screen_lineage(args)
    if args.get("mode") not in (None, "legacy_heuristic"):
        return _error("SCREENING_MODE_UNSUPPORTED")

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
        "mode": "legacy_heuristic",
        "interpretation": "keyword_heuristic_not_competence_proof",
        "extracted": [
            {key: value for key, value in item.items() if key != "text"}
            for item in extracted
        ],
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
        return _error(
            "MAX_TERMS_PER_SOURCE_INVALID", "max_terms_per_source must be positive"
        )

    result = extract_missing_role_terms(
        [str(url) for url in source_urls] if source_urls is not None else None,
        timeout_seconds=timeout_seconds,
        max_terms_per_source=max_terms_per_source,
    )
    return json.dumps(result, ensure_ascii=False)


def _screen_lineage(args: dict[str, Any]) -> str:
    """IO-only adapter; core owns all interpretation and predicate semantics."""
    import hashlib
    import uuid
    from services.resume_screening_lineage import (
        evaluate_lineage,
        load_teaching_basis,
        document_projection,
    )
    from .extraction import list_session_upload_records, _session_env
    from .artifacts import write_screening_artifact

    paths = args.get("resume_paths")
    if not isinstance(paths, list) or len(paths) != 1 or not args.get("jd_path"):
        return _error("LINEAGE_PAIR_REQUIRED")
    manifest = list_session_upload_records()
    if manifest.get("status") != "ok":
        return _error("SESSION_UPLOAD_REQUIRED")
    texts, refs, documents = {}, {}, {}
    for role, query in (("jd", args["jd_path"]), ("resume", paths[0])):
        # Do not use the legacy resolver's arbitrary-path or fuzzy-match fallback.
        matches = [
            item
            for item in manifest["uploads"]
            if query in (item["upload_id"], item["filename"], item["path"])
        ]
        if len(matches) != 1:
            return _error("SESSION_UPLOAD_REQUIRED", role=role)
        record = matches[0]
        path = Path(record["source_path"])
        if path.resolve().parent != Path(manifest["uploads_root"]).resolve():
            return _error("SESSION_UPLOAD_REQUIRED", role=role)
        if path.suffix.lower() not in {".md", ".txt"}:
            return _error("LINEAGE_TEXT_BASIS_REQUIRED", role=role)
        raw = path.read_bytes()
        content_hash = "sha256:" + hashlib.sha256(raw).hexdigest()
        try:
            texts[role] = raw.decode("utf-8")
        except UnicodeDecodeError:
            return _error("LINEAGE_TEXT_ENCODING_INVALID", role=role)
        projection = document_projection(texts[role])
        projection_hash = "sha256:" + hashlib.sha256(projection).hexdigest()
        projection_path = path.parent / (
            role + "-lineage-" + projection_hash[7:] + ".docx"
        )
        try:
            with projection_path.open("xb") as handle:
                handle.write(projection)
        except FileExistsError:
            if (
                projection_path.is_symlink()
                or projection_path.read_bytes() != projection
            ):
                return _error("SOURCE_PROJECTION_CHANGED", role=role)
        refs[role] = projection_hash
        documents[role] = {
            "filename": path.name,
            "upload_id": record["upload_id"],
            "content_hash": content_hash,
            "source_version": content_hash,
            "projection_hash": projection_hash,
            "source_identity_ref": "session-upload:"
            + _session_env("HERMES_SESSION_ID")
            + ":"
            + projection_hash,
            "projection_filename": projection_path.name,
            "projection_version": "lossless_paragraph_docx.v1",
        }
    lineage = evaluate_lineage(texts, load_teaching_basis(), source_refs=refs)
    payload = {
        "status": "ok",
        "mode": "lineage_v1",
        "lineage": lineage,
        "source_documents": documents,
        "legacy_heuristic": False,
    }
    try:
        # Each execution gets a new artifact path; historical results are not overwritten.
        path = write_screening_artifact("lineage-" + uuid.uuid4().hex, payload)
    except RuntimeError as exc:
        return _error(str(exc).split(":", 1)[0], str(exc))
    return json.dumps(dict(payload, artifact_path=str(path)), ensure_ascii=False)
