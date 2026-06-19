from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

SUPPORTED_EXTENSIONS = (".docx", ".md", ".txt")
_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_text(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


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


def extract_text_from_resume(path: Path) -> dict[str, Any]:
    resolved = path.expanduser()
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
    if extension == ".docx":
        raw_text = _read_docx(resolved)
    else:
        raw_text = resolved.read_text(encoding="utf-8")
    text = _normalize_text(raw_text)
    return {
        "status": "ok",
        "source_path": str(resolved),
        "filename": resolved.name,
        "extension": extension,
        "char_count": len(text),
        "text_sha256": _sha256_text(text),
        "text": text,
    }


def extract_text_json(path: str) -> str:
    return json.dumps(extract_text_from_resume(Path(path)), ensure_ascii=False)
