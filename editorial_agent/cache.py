"""Small file-cache layer for web requests.

Caching improves reliability, speed, and token economy. It also makes debugging
easier because a run can explain whether it used live network data or a cached
copy. Cache entries include timestamps; the agent still labels cached material
as cached so humans do not mistake it for fresh live verification.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class FileCache:
    """JSON/text file cache keyed by arbitrary strings."""

    def __init__(self, root: Path, *, enabled: bool = True) -> None:
        self.root = root
        self.enabled = enabled
        self.root.mkdir(parents=True, exist_ok=True)

    def key_path(self, namespace: str, key: str, suffix: str = ".txt") -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        path = self.root / namespace / f"{digest}{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def get_text(self, namespace: str, key: str) -> str | None:
        if not self.enabled:
            return None
        path = self.key_path(namespace, key)
        return path.read_text(encoding="utf-8") if path.exists() else None

    def set_text(self, namespace: str, key: str, value: str) -> None:
        if not self.enabled:
            return
        self.key_path(namespace, key).write_text(value, encoding="utf-8")

    def get_json(self, namespace: str, key: str) -> Any | None:
        if not self.enabled:
            return None
        path = self.key_path(namespace, key, ".json")
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def set_json(self, namespace: str, key: str, value: Any) -> None:
        if not self.enabled:
            return
        self.key_path(namespace, key, ".json").write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


class CachedHttpClient:
    """requests-compatible wrapper that caches get_text/get_json calls."""

    def __init__(self, wrapped, cache: FileCache):
        self.wrapped = wrapped
        self.cache = cache
        self.headers = getattr(wrapped, "headers", {})
        self.timeout = getattr(wrapped, "timeout", None)

    def get_text(self, url: str) -> str:
        cached = self.cache.get_text("http_text", url)
        if cached is not None:
            return cached
        text = self.wrapped.get_text(url)
        self.cache.set_text("http_text", url, text)
        return text

    def get_json(self, url: str) -> dict:
        cached = self.cache.get_json("http_json", url)
        if cached is not None:
            return cached
        data = self.wrapped.get_json(url)
        self.cache.set_json("http_json", url, data)
        return data
