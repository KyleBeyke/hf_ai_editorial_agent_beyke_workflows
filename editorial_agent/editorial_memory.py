"""Durable local editorial memory.

This memory is intentionally user-owned and local. It helps future runs avoid
repeating topics, title patterns, sources, and article angles. It is separate
from WordPress state: a generated draft is not considered published unless a
human-approved publishing action records it as accepted.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .schemas import CandidateTopic, ResearchEvidence, EditorialReview, utc_now_iso
from .similarity import tokens, jaccard


class EditorialMemoryStore:
    """Small JSON-backed memory store for editorial decisions."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.root / name

    def read_json(self, name: str, default: Any) -> Any:
        path = self._path(name)
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def write_json(self, name: str, data: Any) -> None:
        self._path(name).write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    def prior_topic_risk(self, candidate: CandidateTopic) -> tuple[float, str]:
        """Return duplicate risk against previously generated/accepted topics."""

        topics = self.read_json("generated_topics.json", []) + self.read_json("accepted_drafts.json", [])
        cand_tokens = tokens(f"{candidate.title} {candidate.summary}")
        best = (0.0, "")
        for item in topics:
            text = f"{item.get('title','')} {item.get('summary','')} {item.get('angle','')}"
            score = jaccard(cand_tokens, tokens(text))
            if score > best[0]:
                best = (score, item.get("title", "previous topic"))
        if best[0] >= 0.45:
            return round(best[0], 3), f"Similar to prior editorial memory topic: {best[1]}"
        return round(best[0], 3), "No significant local editorial-memory overlap."

    def record_generated_draft(
        self,
        *,
        candidate: CandidateTopic,
        article_path: str,
        run_dir: str,
        evidence: list[ResearchEvidence],
        review: EditorialReview,
    ) -> None:
        """Record a generated draft without treating it as published."""

        generated = self.read_json("generated_topics.json", [])
        generated.append(
            {
                "created_at": utc_now_iso(),
                "title": candidate.title,
                "url": candidate.url,
                "summary": candidate.summary,
                "article_path": article_path,
                "run_dir": run_dir,
                "review_ok": review.ok,
            }
        )
        self.write_json("generated_topics.json", generated[-200:])

        sources = self.read_json("source_quality_history.json", {})
        for ev in evidence:
            entry = sources.setdefault(ev.url, {"title": ev.title, "source_name": ev.source_name, "uses": 0, "authority_score": ev.authority_score})
            entry["uses"] = int(entry.get("uses", 0)) + 1
            entry["last_used_at"] = utc_now_iso()
        self.write_json("source_quality_history.json", sources)

    def record_accepted_draft(self, approval_payload: dict[str, Any], wp_response: dict[str, Any]) -> None:
        """Record that a human accepted a draft-creation action."""

        accepted = self.read_json("accepted_drafts.json", [])
        accepted.append(
            {
                "accepted_at": utc_now_iso(),
                "approval": approval_payload,
                "wordpress_response": wp_response,
            }
        )
        self.write_json("accepted_drafts.json", accepted[-200:])
