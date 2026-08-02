from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..observations import normalize_repository

class GitHubAdapter:
    def __init__(self, token: str | None = None, transport=None):
        self.token = token
        self.transport = transport
        self._etag_cache: dict[str, str] = {}

    def get_repository(self, full_name: str) -> dict:
        if not full_name or full_name.count("/") != 1: raise ValueError("GITHUB_REPOSITORY_INVALID")
        if self.transport is not None: raw = self.transport(full_name, None)
        else:
            # Credentials come from the runtime secret binding, never tool args.
            headers = {"Accept": "application/vnd.github+json"}
            if self.token: headers["Authorization"] = f"Bearer {self.token}"
            request = Request(f"https://api.github.com/repos/{full_name}", headers=headers)
            try:
                with urlopen(request, timeout=20) as response: raw = json.load(response)
            except HTTPError as exc:
                if exc.code == 403: raise RuntimeError("GITHUB_RATE_LIMITED") from exc
                raise RuntimeError(f"GITHUB_HTTP_{exc.code}") from exc
            except URLError as exc: raise RuntimeError("GITHUB_SOURCE_UNAVAILABLE") from exc
        return normalize_repository(raw)

    def search_repositories(self, query: str, *, page: int = 1, per_page: int = 30) -> dict:
        if not query.strip(): raise ValueError("GITHUB_QUERY_REQUIRED")
        if page < 1 or per_page < 1 or per_page > 100: raise ValueError("GITHUB_PAGINATION_INVALID")
        cache_key = f"search:{query}:{page}:{per_page}"
        if self.transport is not None:
            raw, etag = self.transport("search:" + query, {"page": page, "per_page": per_page, "etag": self._etag_cache.get(cache_key)})
            if raw is None: return {"status": "NOT_MODIFIED", "items": [], "page": page, "etag": etag}
        else:
            headers = {"Accept": "application/vnd.github+json"}
            if self.token: headers["Authorization"] = f"Bearer {self.token}"
            if cache_key in self._etag_cache: headers["If-None-Match"] = self._etag_cache[cache_key]
            request = Request(f"https://api.github.com/search/repositories?q={query}&page={page}&per_page={per_page}", headers=headers)
            try:
                with urlopen(request, timeout=20) as response:
                    raw = json.load(response); etag = response.headers.get("ETag")
            except HTTPError as exc:
                if exc.code == 304: return {"status": "NOT_MODIFIED", "items": [], "page": page, "etag": self._etag_cache.get(cache_key)}
                if exc.code == 403: raise RuntimeError("GITHUB_RATE_LIMITED") from exc
                raise RuntimeError(f"GITHUB_HTTP_{exc.code}") from exc
            except URLError as exc: raise RuntimeError("GITHUB_SOURCE_UNAVAILABLE") from exc
        if etag: self._etag_cache[cache_key] = etag
        items = [normalize_repository(item) for item in (raw.get("items") or [])]
        return {"status": "OK", "items": items, "page": page, "etag": etag, "total_count": int(raw.get("total_count") or len(items))}
