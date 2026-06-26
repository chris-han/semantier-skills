from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
import zipfile
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

SUPPORTED_EXTENSIONS = (".docx", ".pdf", ".md", ".txt")
_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_SECTION_OR_FIELD_TERMS = {
    "个人简历",
    "简历",
    "求职意向",
    "工作经历",
    "项目经历",
    "教育背景",
    "专业背景",
    "技能证书",
    "自我评价",
    "联系方式",
    "个人信息",
    "基本信息",
    "证书",
    "姓名",
    "电话",
    "邮箱",
    "现居",
    "生日",
    "性别",
    "民族",
    "籍贯",
    "政治面貌",
    "skill certificate",
    "self evaluation",
    "work experience",
    "professional background",
    "education",
    "experience",
    "resume",
    "curriculum vitae",
    "contact",
}
_ROLE_TERMS = (
    "工程师",
    "设计师",
    "规划师",
    "咨询师",
    "分析师",
    "架构师",
    "医师",
    "律师",
    "教师",
    "讲师",
    "护士",
    "会计",
    "审计",
    "出纳",
    "编辑",
    "记者",
    "翻译",
    "客服",
    "销售",
    "商务",
    "采购",
    "运营",
    "市场",
    "营销",
    "品牌",
    "人事",
    "行政",
    "法务",
    "财务",
    "金融",
    "保险",
    "银行",
    "物流",
    "仓储",
    "司机",
    "厨师",
    "技师",
    "技术员",
    "操作员",
    "维修",
    "生产",
    "质检",
    "品控",
    "开发",
    "经理",
    "主管",
    "总监",
    "负责人",
    "主任",
    "顾问",
    "代表",
    "助理",
    "文员",
    "职员",
    "员工",
    "工人",
    "领班",
    "店长",
    "经纪人",
    "代理人",
    "专员",
    "实习",
    "intern",
    "trainee",
    "assistant",
    "associate",
    "coordinator",
    "administrator",
    "clerk",
    "representative",
    "specialist",
    "consultant",
    "advisor",
    "analyst",
    "planner",
    "officer",
    "director",
    "supervisor",
    "lead",
    "principal",
    "partner",
    "executive",
    "java",
    "python",
    "backend",
    "frontend",
    "engineer",
    "architect",
    "technician",
    "operator",
    "mechanic",
    "developer",
    "designer",
    "manager",
    "accountant",
    "auditor",
    "bookkeeper",
    "cashier",
    "buyer",
    "sales",
    "marketing",
    "operations",
    "recruiter",
    "hr",
    "legal",
    "paralegal",
    "lawyer",
    "attorney",
    "teacher",
    "instructor",
    "professor",
    "nurse",
    "doctor",
    "physician",
    "therapist",
    "pharmacist",
    "editor",
    "writer",
    "translator",
    "driver",
    "chef",
    "cook",
)


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_text(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _collapse_repeated_name(value: str) -> str:
    compact = re.sub(r"\s+", "", value.strip())
    if compact and len(compact) % 2 == 0:
        half = len(compact) // 2
        if compact[:half] == compact[half:]:
            return compact[:half]
    return value.strip()


def _clean_candidate_name(value: str) -> str:
    cleaned = re.sub(r"^(?:姓名|name|candidate)\s*[:：]\s*", "", value.strip(), flags=re.I)
    cleaned = re.split(r"(?:电话|手机|邮箱|email|现居|生日|求职意向)[:：]?", cleaned, maxsplit=1, flags=re.I)[0]
    cleaned = re.sub(r"[\t\r\n|/\\]+", " ", cleaned).strip(" ：:，,。.;；")
    return _collapse_repeated_name(cleaned)


def _looks_like_person_name(value: str) -> bool:
    name = _clean_candidate_name(value)
    if not name:
        return False
    normalized = name.lower()
    if normalized in _SECTION_OR_FIELD_TERMS:
        return False
    if any(term in normalized for term in _SECTION_OR_FIELD_TERMS if len(term) > 1):
        return False
    if any(term in normalized for term in _ROLE_TERMS):
        return False
    if re.search(r"[@\d]", name):
        return False
    if _CJK_RE.search(name):
        compact = re.sub(r"\s+", "", name)
        return 2 <= len(compact) <= 4 and all(
            "\u4e00" <= char <= "\u9fff" for char in compact
        )
    if re.fullmatch(r"[A-Za-z][A-Za-z.'-]*(?: [A-Za-z][A-Za-z.'-]*){0,2}", name):
        return len(name) <= 40
    return False


def extract_candidate_name(text: str) -> str | None:
    normalized = _normalize_text(text)
    lines = normalized.splitlines()

    label_patterns = (
        re.compile(
            r"(?:^|\b)(?:姓名|name|candidate)\s*[:：]\s*"
            r"([A-Za-z][A-Za-z.' -]{0,39}|[\u4e00-\u9fff]{2,4})",
            re.I,
        ),
    )
    for line in lines:
        for pattern in label_patterns:
            match = pattern.search(line)
            if match:
                candidate = _clean_candidate_name(match.group(1))
                if _looks_like_person_name(candidate):
                    return candidate

    previous = ""
    for line in lines[:80]:
        candidate = _clean_candidate_name(line)
        if _looks_like_person_name(candidate):
            return candidate
        if line == previous:
            collapsed = _clean_candidate_name(line)
            if _looks_like_person_name(collapsed):
                return collapsed
        previous = line

    return None


def _read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        raw = archive.read("word/document.xml")
    root = ElementTree.fromstring(raw)
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{_WORD_NS}p"):
        chunks = [node.text or "" for node in paragraph.iter(f"{_WORD_NS}t")]
        text = "".join(chunks).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def _read_pdf(path: Path) -> str:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise RuntimeError(
            "PDF_EXTRACTION_DEPENDENCY_MISSING: pypdfium2 is required for PDF extraction"
        ) from exc

    doc = pdfium.PdfDocument(str(path))
    try:
        pages: list[str] = []
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            text = page.get_textpage().get_text_range().strip()
            if text:
                pages.append(text)
        return "\n".join(pages)
    finally:
        close = getattr(doc, "close", None)
        if callable(close):
            close()


def _session_env(name: str) -> str:
    try:
        from gateway.session_context import get_session_env

        return get_session_env(name, "") or os.getenv(name, "")
    except Exception:
        return os.getenv(name, "")


def _active_workspace_home() -> str:
    try:
        from runtime_paths import current_workspace_hermes_home

        value = current_workspace_hermes_home()
        if value:
            return value
    except Exception:
        pass
    return _session_env("HERMES_SESSION_HERMES_HOME") or os.getenv("HERMES_HOME", "")


def _filename_lookup_key(name: str) -> str:
    return re.sub(r"\s*-\s*", "-", name.strip())


def _filename_match_key(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", name).casefold().strip()
    normalized = re.sub(r"[\u2010-\u2015\u2212\uff0d]+", "-", normalized)
    normalized = re.sub(r"[\s_\-]+", "", normalized)
    return normalized


def _upload_id_for_path(path: Path) -> str:
    return hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:16]


def _session_uploads_root() -> Path | None:
    workspace_home = _active_workspace_home().strip()
    session_id = _session_env("HERMES_SESSION_ID").strip()
    if not workspace_home or not session_id:
        return None
    try:
        from runtime_paths import workspace_session_runs_root_from_hermes_home

        return (
            workspace_session_runs_root_from_hermes_home(Path(workspace_home), session_id).parent
            / "uploads"
        ).resolve()
    except Exception:
        return None


def list_session_upload_records() -> dict[str, Any]:
    uploads_root = _session_uploads_root()
    if uploads_root is None:
        return {
            "status": "error",
            "error_code": "SESSION_UPLOADS_CONTEXT_REQUIRED",
            "message": "Active workspace/session context is required to list uploads.",
        }
    if not uploads_root.exists():
        return {"status": "ok", "uploads_root": str(uploads_root), "uploads": []}
    records = []
    for candidate in sorted(uploads_root.iterdir(), key=lambda item: item.name):
        if not candidate.is_file():
            continue
        extension = candidate.suffix.lower()
        records.append(
            {
                "upload_id": _upload_id_for_path(candidate),
                "filename": candidate.name,
                "path": f"uploads/{candidate.name}",
                "source_path": str(candidate.resolve()),
                "extension": extension,
                "size_bytes": candidate.stat().st_size,
                "supported": extension in SUPPORTED_EXTENSIONS,
            }
        )
    return {"status": "ok", "uploads_root": str(uploads_root), "uploads": records}


def resolve_uploaded_resume_path(query: str) -> dict[str, Any]:
    raw = str(query or "").strip()
    if not raw:
        return {
            "status": "error",
            "error_code": "UPLOAD_QUERY_REQUIRED",
            "message": "A resume filename, uploads path, or upload_id is required.",
        }

    direct = Path(raw).expanduser()
    if direct.exists():
        return {
            "status": "ok",
            "query": raw,
            "source_path": str(direct.resolve()),
            "filename": direct.name,
            "resolution": "direct_path",
        }

    manifest = list_session_upload_records()
    if manifest.get("status") != "ok":
        return manifest
    uploads = [item for item in manifest["uploads"] if item.get("supported")]
    if not uploads:
        return {
            "status": "error",
            "error_code": "NO_SUPPORTED_UPLOADS",
            "message": "No supported resume uploads are available in the active session.",
        }

    query_path = Path(raw)
    query_filename = query_path.name
    query_upload_path = raw if raw.startswith("uploads/") else f"uploads/{query_filename}"

    exact = [
        record
        for record in uploads
        if raw == record["upload_id"]
        or raw == record["filename"]
        or raw == record["path"]
        or query_upload_path == record["path"]
    ]
    if len(exact) == 1:
        record = exact[0]
        return {
            "status": "ok",
            "query": raw,
            "source_path": record["source_path"],
            "filename": record["filename"],
            "upload_id": record["upload_id"],
            "resolution": "exact",
        }
    if len(exact) > 1:
        return {
            "status": "error",
            "error_code": "UPLOAD_RESOLUTION_AMBIGUOUS",
            "query": raw,
            "candidates": exact,
        }

    query_key = _filename_match_key(query_filename)
    normalized = [
        record for record in uploads if _filename_match_key(str(record["filename"])) == query_key
    ]
    if len(normalized) == 1:
        record = normalized[0]
        return {
            "status": "ok",
            "query": raw,
            "source_path": record["source_path"],
            "filename": record["filename"],
            "upload_id": record["upload_id"],
            "resolution": "normalized_filename",
        }
    if len(normalized) > 1:
        return {
            "status": "error",
            "error_code": "UPLOAD_RESOLUTION_AMBIGUOUS",
            "query": raw,
            "candidates": normalized,
        }

    scored = [
        (
            SequenceMatcher(
                None,
                query_key,
                _filename_match_key(str(record["filename"])),
            ).ratio(),
            record,
        )
        for record in uploads
    ]
    scored = [(score, record) for score, record in scored if score >= 0.88]
    scored.sort(key=lambda item: (-item[0], str(item[1]["filename"])))
    if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        score, record = scored[0]
        return {
            "status": "ok",
            "query": raw,
            "source_path": record["source_path"],
            "filename": record["filename"],
            "upload_id": record["upload_id"],
            "resolution": "close_filename",
            "confidence": round(score, 4),
        }
    if scored:
        return {
            "status": "error",
            "error_code": "UPLOAD_RESOLUTION_AMBIGUOUS",
            "query": raw,
            "candidates": [record for _score, record in scored],
        }
    return {
        "status": "error",
        "error_code": "UPLOAD_NOT_FOUND",
        "query": raw,
        "available_uploads": uploads,
    }


def _resolve_hyphen_spacing_variant(path: Path) -> Path | None:
    parent = path.parent
    if not parent.exists() or not parent.is_dir():
        return None
    lookup_key = _filename_lookup_key(path.name)
    matches = [
        candidate
        for candidate in parent.iterdir()
        if candidate.is_file() and _filename_lookup_key(candidate.name) == lookup_key
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def _resolve_resume_path(path: Path) -> Path:
    expanded = path.expanduser()
    if expanded.exists():
        return expanded
    sibling_variant = _resolve_hyphen_spacing_variant(expanded)
    if sibling_variant is not None:
        return sibling_variant
    if expanded.is_absolute():
        return expanded
    if not path.parts or path.parts[0] != "uploads":
        return expanded

    relative_parts = path.parts[1:]
    if not relative_parts or any(part in {"", ".", ".."} for part in relative_parts):
        return expanded

    workspace_home = _active_workspace_home().strip()
    session_id = _session_env("HERMES_SESSION_ID").strip()
    if not workspace_home or not session_id:
        return expanded

    uploads_root = _session_uploads_root()
    if uploads_root is None:
        return expanded
    candidate = (uploads_root / Path(*relative_parts)).resolve()
    resolved_root = uploads_root.resolve()
    if candidate != resolved_root and resolved_root in candidate.parents:
        sibling_variant = _resolve_hyphen_spacing_variant(candidate)
        if sibling_variant is not None:
            return sibling_variant
        return candidate
    return expanded


def extract_text_from_resume(path: Path) -> dict[str, Any]:
    resolved = _resolve_resume_path(path)
    if not resolved.exists():
        return {
            "status": "error",
            "error_code": "RESUME_FILE_MISSING",
            "message": f"Resume file not found: {path}",
        }
    extension = resolved.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        return {
            "status": "error",
            "error_code": "UNSUPPORTED_RESUME_FORMAT",
            "message": f"Supported resume formats: {', '.join(SUPPORTED_EXTENSIONS)}",
            "extension": extension,
        }
    try:
        if extension == ".docx":
            raw_text = _read_docx(resolved)
        elif extension == ".pdf":
            raw_text = _read_pdf(resolved)
        else:
            raw_text = resolved.read_text(encoding="utf-8")
    except RuntimeError as exc:
        code = str(exc).split(":", 1)[0]
        return {
            "status": "error",
            "error_code": code,
            "message": str(exc),
            "extension": extension,
        }
    text = _normalize_text(raw_text)
    candidate_name = extract_candidate_name(text)
    return {
        "status": "ok",
        "source_path": str(resolved),
        "filename": resolved.name,
        "extension": extension,
        "extraction_method": "pypdfium2_text" if extension == ".pdf" else "native_text",
        "char_count": len(text),
        "text_sha256": _sha256_text(text),
        "candidate_name": candidate_name,
        "text": text,
    }


def extract_text_json(path: str) -> str:
    return json.dumps(extract_text_from_resume(Path(path)), ensure_ascii=False)
