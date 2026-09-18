from __future__ import annotations

import hashlib
import html
import io
import ipaddress
import json
import os
import re
import socket
import urllib.error
import urllib.request
import zipfile
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlsplit


BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36"
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _error(code: str, message: str, **extra: Any) -> str:
    return _json({"ok": False, "error_code": code, "message": message, **extra})


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return cleaned or "collection"


def _workspace_runs_dir() -> Path:
    raw = os.environ.get("SEMANTIER_WORKSPACE_RUNS_DIR")
    if not raw:
        try:
            from runtime_paths import current_workspace_runs_dir

            raw = current_workspace_runs_dir()
        except Exception:
            raw = None
    if not raw:
        raise RuntimeError(
            "WORKSPACE_RUNS_DIR_REQUIRED: SEMANTIER_WORKSPACE_RUNS_DIR is required"
        )
    return Path(raw).expanduser()


def _collection_root(collection_id: str) -> Path:
    return _workspace_runs_dir() / "resilient_public_data_collection" / _slug(collection_id)


def _resolve_public_ips(hostname: str) -> list[str]:
    results = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    return sorted({entry[4][0] for entry in results})


def _validate_public_url(url: str) -> str:
    parts = urlsplit(str(url).strip())
    if parts.scheme not in {"http", "https"}:
        raise ValueError("only public HTTP(S) URLs are supported")
    if not parts.hostname or parts.username or parts.password:
        raise ValueError("URL must have a hostname and no embedded credentials")
    if parts.hostname.lower() == "localhost":
        raise ValueError("localhost is not a public source")
    addresses = _resolve_public_ips(parts.hostname)
    if not addresses:
        raise ValueError("hostname did not resolve")
    for raw in addresses:
        address = ipaddress.ip_address(raw)
        if not address.is_global:
            raise ValueError(f"non-public address blocked: {raw}")
    return url


class _PublicRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    result = int(value if value is not None else default)
    if not minimum <= result <= maximum:
        raise ValueError(f"value must be between {minimum} and {maximum}")
    return result


def _request_bytes(
    *,
    url: str,
    referer: str | None,
    timeout_seconds: float,
    max_bytes: int,
    allow_truncate: bool = False,
) -> tuple[dict[str, Any], bytes]:
    _validate_public_url(url)
    headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        "Accept-Encoding": "identity",
    }
    if referer:
        _validate_public_url(referer)
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(_PublicRedirectHandler())
    try:
        response = opener.open(request, timeout=timeout_seconds)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        final_url = response.geturl()
        _validate_public_url(final_url)
        body = response.read(max_bytes + 1)
        truncated = len(body) > max_bytes
        if truncated and not allow_truncate:
            raise ValueError(f"response exceeds max_bytes={max_bytes}")
        if truncated:
            body = body[:max_bytes]
        metadata = {
            "requested_url": url,
            "request_referer": referer,
            "final_url": final_url,
            "http_status": int(response.status),
            "truncated": truncated,
            "response_headers": {
                key: value
                for key, value in response.headers.items()
                if key.lower()
                in {
                    "content-type",
                    "content-length",
                    "content-disposition",
                    "location",
                    "server",
                    "ws-action",
                }
            },
        }
        return metadata, body


def _access_signal(status: int, headers: dict[str, str]) -> str:
    lowered = {key.lower(): value for key, value in headers.items()}
    if lowered.get("ws-action"):
        return "WAF_OR_ANTI_BOT"
    if status in {401, 403}:
        return "AUTH_OR_ACCESS_BLOCKED"
    if status == 429:
        return "RATE_LIMITED"
    if 200 <= status < 300:
        return "PUBLIC_RESPONSE"
    return "HTTP_ERROR"


def _content_disposition_filename(headers: dict[str, str]) -> str | None:
    value = ""
    for key, candidate in headers.items():
        if key.lower() == "content-disposition":
            value = candidate
            break
    if not value:
        return None
    encoded = re.search(r"filename\*=UTF-8''([^;]+)", value, flags=re.I)
    if encoded:
        from urllib.parse import unquote

        return unquote(encoded.group(1))
    quoted = re.search(r'filename="?([^";]+)"?', value, flags=re.I)
    return quoted.group(1).strip() if quoted else None


def _detect_format(data: bytes) -> dict[str, Any]:
    stripped = data[:2048].lstrip()
    lower = stripped.lower()
    if data.startswith(b"%PDF-"):
        eof_ok = b"%%EOF" in data[-8192:]
        return {"format": "pdf", "document_like": eof_ok, "detail": "eof_ok" if eof_ok else "missing_eof"}
    if zipfile.is_zipfile(io.BytesIO(data)):
        return {"format": "zip_container", "document_like": True}
    if data.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
        return {"format": "ole_document", "document_like": True}
    if data.startswith((b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00")):
        return {"format": "rar_container", "document_like": True}
    if data.startswith(bytes.fromhex("377abcaf271c")):
        return {"format": "7z_container", "document_like": True}
    if lower.startswith((b"<!doctype html", b"<html", b"<script")):
        return {"format": "html", "document_like": False}
    if lower.startswith(b"<?xml"):
        return {"format": "xml", "document_like": False}
    try:
        json.loads(data.decode("utf-8"))
    except Exception:
        pass
    else:
        return {"format": "json", "document_like": False}
    return {"format": "unknown", "document_like": False}


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self._in_title = False
        self.current_anchor: dict[str, str] | None = None
        self.anchors: list[dict[str, str]] = []
        self.scripts: list[str] = []
        self.forms: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "a":
            self.current_anchor = {**values, "text": ""}
        elif tag == "script" and values.get("src"):
            self.scripts.append(values["src"])
        elif tag == "form" and values.get("action"):
            self.forms.append(values["action"])

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self.current_anchor is not None:
            self.current_anchor["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "a" and self.current_anchor is not None:
            self.anchors.append(self.current_anchor)
            self.current_anchor = None


_ATTACHMENT_HINT = re.compile(
    r"download|attach|附件|招标文件|采购文件|磋商文件|谈判文件|询价文件|采购需求|"
    r"\.(?:pdf|zip|docx?|xlsx?|rar|7z)(?:$|[?#])",
    flags=re.I,
)


def _inspect_html(page_url: str, body: bytes, max_links: int) -> dict[str, Any]:
    text = body.decode("utf-8", "replace")
    parser = _AnchorParser()
    parser.feed(text)
    host = (urlsplit(page_url).hostname or "").lower()
    candidates: list[dict[str, Any]] = []
    ordinary_links: list[dict[str, str]] = []

    for anchor in parser.anchors[:max_links]:
        href = html.unescape(anchor.get("href", "")).strip()
        label = re.sub(r"\s+", " ", anchor.get("text", "")).strip()
        classes = anchor.get("class", "")
        anchor_id = anchor.get("id", "")
        resolved = urljoin(page_url, href) if href else None
        ordinary_links.append({"text": label, "href": resolved or ""})
        if (
            _ATTACHMENT_HINT.search(" ".join([href, label, classes]))
            or "bizDownload" in classes.split()
        ):
            item: dict[str, Any] = {
                "text": label,
                "href": resolved,
                "id": anchor_id or None,
                "class": classes or None,
            }
            if (
                (host == "ccgp.gov.cn" or host.endswith(".ccgp.gov.cn"))
                and "bizDownload" in classes.split()
                and re.fullmatch(r"[A-Za-z0-9-]{8,80}", anchor_id)
            ):
                item["derived_public_url"] = (
                    "https://download.ccgp.gov.cn/oss/download?uuid="
                    + quote(anchor_id, safe="-")
                )
                item["derivation"] = "CCGP_BIZDOWNLOAD_UUID"
            candidates.append(item)

    return {
        "title": re.sub(r"\s+", " ", "".join(parser.title_parts)).strip(),
        "attachment_candidates": candidates,
        "links": ordinary_links,
        "scripts": [urljoin(page_url, item) for item in parser.scripts[:max_links]],
        "forms": [urljoin(page_url, item) for item in parser.forms[:max_links]],
    }


def probe_public_url(args: dict[str, Any], **_kw: Any) -> str:
    url = str(args.get("url") or "").strip()
    if not url:
        return _error("URL_REQUIRED", "url is required")
    referer = str(args.get("referer") or "").strip() or None
    try:
        timeout = float(args.get("timeout_seconds") or 20)
        if not 1 <= timeout <= 60:
            raise ValueError("timeout_seconds must be between 1 and 60")
        sample_bytes = _bounded_int(args.get("sample_bytes"), 65536, 1, 262144)
        metadata, body = _request_bytes(
            url=url,
            referer=referer,
            timeout_seconds=timeout,
            max_bytes=sample_bytes,
            allow_truncate=True,
        )
    except Exception as exc:
        return _error("PUBLIC_PROBE_FAILED", str(exc), requested_url=url)

    sample = body[:2048]
    preview = sample.decode("utf-8", "replace") if sample else ""
    return _json(
        {
            "ok": True,
            **metadata,
            "access_signal": _access_signal(
                metadata["http_status"], metadata["response_headers"]
            ),
            "sample_bytes": len(body),
            "sample_sha256": hashlib.sha256(body).hexdigest(),
            "sample_preview": preview,
        }
    )


def inspect_public_page(args: dict[str, Any], **_kw: Any) -> str:
    url = str(args.get("url") or "").strip()
    if not url:
        return _error("URL_REQUIRED", "url is required")
    referer = str(args.get("referer") or "").strip() or None
    try:
        timeout = float(args.get("timeout_seconds") or 20)
        if not 1 <= timeout <= 60:
            raise ValueError("timeout_seconds must be between 1 and 60")
        max_html_bytes = _bounded_int(
            args.get("max_html_bytes"), 2 * 1024 * 1024, 1024, 5 * 1024 * 1024
        )
        max_links = _bounded_int(args.get("max_links"), 200, 1, 1000)
        metadata, body = _request_bytes(
            url=url,
            referer=referer,
            timeout_seconds=timeout,
            max_bytes=max_html_bytes,
        )
        inspection = _inspect_html(metadata["final_url"], body, max_links)
    except Exception as exc:
        return _error("PUBLIC_PAGE_INSPECTION_FAILED", str(exc), requested_url=url)

    return _json(
        {
            "ok": True,
            **metadata,
            "access_signal": _access_signal(
                metadata["http_status"], metadata["response_headers"]
            ),
            "page_sha256": hashlib.sha256(body).hexdigest(),
            "page_bytes": len(body),
            **inspection,
        }
    )


def _write_json_once(path: Path, value: dict[str, Any]) -> None:
    data = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(data)
    except FileExistsError:
        if path.read_bytes() != data:
            raise ValueError(f"immutable artifact already exists: {path}")


def freeze_public_membership(args: dict[str, Any], **_kw: Any) -> str:
    collection_id = str(args.get("collection_id") or "").strip()
    members = args.get("members")
    if not collection_id or not isinstance(members, list) or not members:
        return _error(
            "ARGUMENT_REQUIRED",
            "collection_id and a non-empty members array are required",
        )
    try:
        root = _collection_root(collection_id)
        if (root / "freeze-manifest.json").exists():
            return _error(
                "COLLECTION_FROZEN",
                "collection already has a release freeze; use a new collection_id",
            )
        if any((root / "receipts").glob("*.json")):
            return _error(
                "MEMBERSHIP_FREEZE_TOO_LATE",
                "capture receipts already exist; freeze membership in a new collection",
            )
        normalized: list[dict[str, Any]] = []
        source_ids: set[str] = set()
        request_keys: set[tuple[str, str | None]] = set()
        for raw in members:
            if not isinstance(raw, dict):
                raise ValueError("each member must be an object")
            source_id = str(raw.get("source_id") or "").strip()
            url = str(raw.get("url") or "").strip()
            referer = str(raw.get("referer") or "").strip() or None
            if not source_id or not url:
                raise ValueError("each member requires source_id and url")
            _validate_public_url(url)
            if referer:
                _validate_public_url(referer)
            if source_id in source_ids:
                raise ValueError(f"duplicate source_id: {source_id}")
            request_key = (url, referer)
            if request_key in request_keys:
                raise ValueError(f"duplicate request member: {url}")
            source_ids.add(source_id)
            request_keys.add(request_key)
            normalized.append(
                {
                    "source_id": source_id,
                    "url": url,
                    "referer": referer,
                    "source_stratum": str(raw.get("source_stratum") or "").strip() or None,
                    "metadata": dict(raw.get("metadata") or {}),
                }
            )

        stable = {
            "collection_id": _slug(collection_id),
            "members": normalized,
            "member_count": len(normalized),
        }
        membership_hash = hashlib.sha256(
            json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        manifest = {
            **stable,
            "frozen_at": _utc_now(),
            "membership_content_hash": membership_hash,
        }
        path = root / "membership-freeze.json"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            comparable_existing = {
                key: value for key, value in existing.items() if key != "frozen_at"
            }
            comparable_manifest = {
                key: value for key, value in manifest.items() if key != "frozen_at"
            }
            if comparable_existing != comparable_manifest:
                return _error(
                    "FROZEN_MEMBERSHIP_MISMATCH",
                    "existing membership freeze differs from requested members",
                )
            return _json({"ok": True, "cached": True, "membership": existing})
        _write_json_once(path, manifest)
    except Exception as exc:
        return _error("MEMBERSHIP_FREEZE_FAILED", str(exc))

    return _json({"ok": True, "cached": False, "membership": manifest})


def capture_public_object(args: dict[str, Any], **_kw: Any) -> str:
    collection_id = str(args.get("collection_id") or "").strip()
    url = str(args.get("url") or "").strip()
    if not collection_id or not url:
        return _error("ARGUMENT_REQUIRED", "collection_id and url are required")
    referer = str(args.get("referer") or "").strip() or None
    attempt = _slug(str(args.get("attempt") or "initial"))
    try:
        timeout = float(args.get("timeout_seconds") or 30)
        if not 1 <= timeout <= 60:
            raise ValueError("timeout_seconds must be between 1 and 60")
        max_bytes = _bounded_int(
            args.get("max_bytes"), 50 * 1024 * 1024, 1024, 100 * 1024 * 1024
        )
        root = _collection_root(collection_id)
        if (root / "freeze-manifest.json").exists():
            return _error(
                "COLLECTION_FROZEN",
                "collection already has a release freeze; use a new collection_id",
            )

        source_id = None
        membership_path = root / "membership-freeze.json"
        if membership_path.exists():
            membership = json.loads(membership_path.read_text(encoding="utf-8"))
            matched = [
                item
                for item in membership["members"]
                if item["url"] == url and item.get("referer") == referer
            ]
            if len(matched) != 1:
                return _error(
                    "REQUEST_NOT_IN_FROZEN_MEMBERSHIP",
                    "url and referer are not a member of the frozen source universe",
                )
            source_id = matched[0]["source_id"]

        capture_key = hashlib.sha256(
            json.dumps(
                {"url": url, "referer": referer, "attempt": attempt},
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        receipt_path = root / "receipts" / f"{capture_key}.json"
        if receipt_path.exists():
            stored = json.loads(receipt_path.read_text(encoding="utf-8"))
            object_relpath = stored.get("object_path")
            if object_relpath:
                object_path = root / object_relpath
                data = object_path.read_bytes()
                if hashlib.sha256(data).hexdigest() != stored.get("sha256"):
                    return _error("CACHED_OBJECT_HASH_MISMATCH", str(object_path))
            return _json({"ok": True, "cached": True, "receipt": stored})

        try:
            metadata, body = _request_bytes(
                url=url,
                referer=referer,
                timeout_seconds=timeout,
                max_bytes=max_bytes,
            )
        except Exception as request_error:
            failure_receipt = {
                "collection_id": _slug(collection_id),
                "source_id": source_id,
                "requested_url": url,
                "request_referer": referer,
                "attempt": attempt,
                "captured_at": _utc_now(),
                "status": "CAPTURE_FAILED",
                "error": f"{type(request_error).__name__}: {request_error}",
            }
            _write_json_once(receipt_path, failure_receipt)
            return _json(
                {
                    "ok": False,
                    "error_code": "PUBLIC_OBJECT_CAPTURE_FAILED",
                    "message": str(request_error),
                    "receipt": failure_receipt,
                }
            )
        sha = hashlib.sha256(body).hexdigest()
        object_path = root / "objects" / sha
        object_path.parent.mkdir(parents=True, exist_ok=True)
        if object_path.exists():
            if object_path.read_bytes() != body:
                raise ValueError("content-addressed object collision")
        else:
            with object_path.open("xb") as stream:
                stream.write(body)

        format_info = _detect_format(body)
        receipt = {
            **metadata,
            "collection_id": _slug(collection_id),
            "source_id": source_id,
            "attempt": attempt,
            "captured_at": _utc_now(),
            "bytes": len(body),
            "sha256": sha,
            "object_path": str(object_path.relative_to(root)),
            "filename": _content_disposition_filename(metadata["response_headers"]),
            "access_signal": _access_signal(
                metadata["http_status"], metadata["response_headers"]
            ),
            **format_info,
        }
        receipt["status"] = (
            "BYTE_VALIDATED_DOCUMENT"
            if metadata["http_status"] == 200 and format_info["document_like"]
            else "CAPTURED_NON_DOCUMENT_OR_ERROR"
        )
        _write_json_once(receipt_path, receipt)
    except Exception as exc:
        return _error("PUBLIC_OBJECT_CAPTURE_FAILED", str(exc), requested_url=url)

    return _json({"ok": True, "cached": False, "receipt": receipt})


def _receipt_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_public_collection(args: dict[str, Any], **_kw: Any) -> str:
    collection_id = str(args.get("collection_id") or "").strip()
    if not collection_id:
        return _error("COLLECTION_ID_REQUIRED", "collection_id is required")
    try:
        root = _collection_root(collection_id)
        receipts = sorted((root / "receipts").glob("*.json"))
        if not receipts:
            return _error("NO_CAPTURE_RECEIPTS", "no capture receipts exist")
        manifest_path = root / "freeze-manifest.json"
        membership_path = root / "membership-freeze.json"
        membership_hash = None
        expected_source_ids: set[str] = set()
        if membership_path.exists():
            membership = json.loads(membership_path.read_text(encoding="utf-8"))
            stable_membership = {
                "collection_id": membership["collection_id"],
                "members": membership["members"],
                "member_count": membership["member_count"],
            }
            computed_membership_hash = hashlib.sha256(
                json.dumps(
                    stable_membership,
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            if computed_membership_hash != membership.get("membership_content_hash"):
                return _error(
                    "MEMBERSHIP_HASH_MISMATCH",
                    "membership freeze content hash does not replay",
                )
            membership_hash = computed_membership_hash
            expected_source_ids = {
                str(item["source_id"]) for item in membership["members"]
            }

        members = []
        statuses: dict[str, int] = {}
        object_hashes: set[str] = set()
        captured_source_ids: set[str] = set()
        total_bytes = 0
        for receipt_path in receipts:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            statuses[receipt["status"]] = statuses.get(receipt["status"], 0) + 1
            if receipt.get("source_id"):
                captured_source_ids.add(str(receipt["source_id"]))
            if receipt.get("sha256"):
                object_hashes.add(receipt["sha256"])
                total_bytes += int(receipt.get("bytes") or 0)
            members.append(
                {
                    "receipt": str(receipt_path.relative_to(root)),
                    "receipt_sha256": _receipt_digest(receipt_path),
                    "object_sha256": receipt.get("sha256"),
                    "source_id": receipt.get("source_id"),
                    "status": receipt.get("status"),
                }
            )

        if expected_source_ids:
            missing_source_ids = sorted(expected_source_ids - captured_source_ids)
            if missing_source_ids:
                return _error(
                    "FROZEN_MEMBERSHIP_INCOMPLETE",
                    "not every frozen member has at least one capture receipt",
                    missing_source_ids=missing_source_ids,
                )

        stable_basis = {
            "collection_id": _slug(collection_id),
            "membership_content_hash": membership_hash,
            "members": members,
            "receipt_count": len(members),
            "unique_object_hashes": len(object_hashes),
            "captured_bytes_sum": total_bytes,
            "status_counts": statuses,
        }
        manifest_hash = hashlib.sha256(
            json.dumps(stable_basis, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        basis = {
            **stable_basis,
            "frozen_at": _utc_now(),
            "manifest_content_hash": manifest_hash,
        }
        if manifest_path.exists():
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            comparable_existing = {
                key: value
                for key, value in existing.items()
                if key != "frozen_at"
            }
            comparable_basis = {
                key: value
                for key, value in basis.items()
                if key != "frozen_at"
            }
            if comparable_existing != comparable_basis:
                return _error(
                    "FROZEN_MANIFEST_MISMATCH",
                    "existing freeze does not match current receipt set",
                )
            return _json({"ok": True, "cached": True, "manifest": existing})
        _write_json_once(manifest_path, basis)
    except Exception as exc:
        return _error("COLLECTION_FREEZE_FAILED", str(exc))

    return _json({"ok": True, "cached": False, "manifest": basis})


def verify_public_collection(args: dict[str, Any], **_kw: Any) -> str:
    collection_id = str(args.get("collection_id") or "").strip()
    if not collection_id:
        return _error("COLLECTION_ID_REQUIRED", "collection_id is required")
    try:
        root = _collection_root(collection_id)
        manifest_path = root / "freeze-manifest.json"
        if not manifest_path.exists():
            return _error("FREEZE_MANIFEST_MISSING", "collection is not frozen")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        stable_manifest = {
            key: value
            for key, value in manifest.items()
            if key not in {"frozen_at", "manifest_content_hash"}
        }
        computed_manifest_hash = hashlib.sha256(
            json.dumps(stable_manifest, ensure_ascii=False, sort_keys=True).encode(
                "utf-8"
            )
        ).hexdigest()
        if computed_manifest_hash != manifest.get("manifest_content_hash"):
            return _error(
                "MANIFEST_HASH_MISMATCH",
                "release freeze content hash does not replay",
            )

        expected_receipts = {member["receipt"] for member in manifest["members"]}
        actual_receipts = {
            str(path.relative_to(root))
            for path in (root / "receipts").glob("*.json")
        }
        if actual_receipts != expected_receipts:
            return _error(
                "RECEIPT_SET_MISMATCH",
                "receipt directory no longer matches frozen membership",
                missing=sorted(expected_receipts - actual_receipts),
                unexpected=sorted(actual_receipts - expected_receipts),
            )

        membership_hash = manifest.get("membership_content_hash")
        if membership_hash:
            membership_path = root / "membership-freeze.json"
            if not membership_path.exists():
                return _error(
                    "MEMBERSHIP_FREEZE_MISSING",
                    "release freeze references a missing membership freeze",
                )
            membership = json.loads(membership_path.read_text(encoding="utf-8"))
            stable_membership = {
                "collection_id": membership["collection_id"],
                "members": membership["members"],
                "member_count": membership["member_count"],
            }
            computed_membership_hash = hashlib.sha256(
                json.dumps(
                    stable_membership,
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            if (
                computed_membership_hash != membership_hash
                or computed_membership_hash
                != membership.get("membership_content_hash")
            ):
                return _error(
                    "MEMBERSHIP_HASH_MISMATCH",
                    "membership freeze no longer matches release binding",
                )

        checked = 0
        for member in manifest["members"]:
            receipt_path = root / member["receipt"]
            if _receipt_digest(receipt_path) != member["receipt_sha256"]:
                return _error(
                    "RECEIPT_HASH_MISMATCH",
                    str(receipt_path),
                )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            object_relpath = receipt.get("object_path")
            if object_relpath:
                object_path = root / object_relpath
                data = object_path.read_bytes()
                if hashlib.sha256(data).hexdigest() != receipt["sha256"]:
                    return _error("OBJECT_HASH_MISMATCH", str(object_path))
                if len(data) != int(receipt["bytes"]):
                    return _error("OBJECT_LENGTH_MISMATCH", str(object_path))
            checked += 1
    except Exception as exc:
        return _error("COLLECTION_VERIFY_FAILED", str(exc))

    return _json(
        {
            "ok": True,
            "collection_id": manifest["collection_id"],
            "verified_receipts": checked,
            "manifest_content_hash": manifest["manifest_content_hash"],
            "status": "OFFLINE_REPLAY_VERIFIED",
        }
    )
