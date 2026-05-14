"""File IO helpers for final article artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json(path: Path, data: Any) -> None:
    """Write stable, human-readable JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    """Write UTF-8 text and create parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def slugify(text: str, fallback: str = "ai-editorial-article") -> str:
    """Create a filesystem/URL friendly slug."""
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:80] or fallback
