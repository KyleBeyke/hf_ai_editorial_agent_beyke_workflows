"""Candidate scoring and selection.

This module is where "best candidate" becomes explainable. The agent scores a
topic using recentness, business relevance, technical relevance, and duplicate
risk against beykeworkflows.com. The model is not asked to invent the score; it uses
the score as evidence when drafting.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from .schemas import CandidateTopic, SourceItem, SiteArticle
from .scrapers import parse_datetime
from .similarity import duplicate_risk


BUSINESS_TERMS = {
    "business", "enterprise", "workflow", "product", "customer", "cost", "governance",
    "risk", "strategy", "operations", "implementation", "reliability", "automation",
    "security", "privacy", "evaluation", "benchmarks", "roi", "deployment",
}

TECHNICAL_TERMS = {
    "agent", "agents", "llm", "model", "models", "inference", "retrieval", "rag",
    "mcp", "context", "structured", "outputs", "eval", "evaluation", "fine-tuning",
    "multimodal", "latency", "tokens", "reasoning", "tool", "tools", "memory",
}


class CandidateSelector:
    """Turn raw source items into scored, duplicate-checked candidates."""

    def build_candidates(
        self, source_items: list[SourceItem], site_articles: list[SiteArticle]
    ) -> list[CandidateTopic]:
        candidates: list[CandidateTopic] = []

        for item in source_items:
            cand = CandidateTopic(
                title=item.title,
                url=item.url,
                source_name=item.source_name,
                published=item.published,
                summary=item.summary,
            )
            cand.business_relevance = keyword_score(f"{cand.title} {cand.summary}", BUSINESS_TERMS)
            cand.technical_relevance = keyword_score(f"{cand.title} {cand.summary}", TECHNICAL_TERMS)
            cand.recency_score = recency_score(cand.published)
            cand.duplicate_risk, cand.duplicate_reason = duplicate_risk(cand, site_articles)

            # Main scoring formula. Duplicate risk is a heavy penalty because the
            # user's requirement is specifically to avoid partial duplicates.
            base = (
                0.35 * cand.recency_score
                + 0.30 * cand.business_relevance
                + 0.30 * cand.technical_relevance
                + 0.05 * source_quality(cand.source_name)
            )
            penalty = 0.95 * max(0.0, cand.duplicate_risk - 0.35)
            cand.score = round(max(0.0, base - penalty), 4)
            candidates.append(cand)

        candidates.sort(key=lambda c: c.score, reverse=True)

        # Select the highest-scoring candidate that is not an exact/near duplicate.
        for cand in candidates:
            if cand.duplicate_risk < 0.70:
                cand.selected = True
                break

        return candidates


def keyword_score(text: str, terms: set[str]) -> float:
    """Score how many relevant terms are present, normalized to 0..1."""
    normalized = re.sub(r"[^a-z0-9\s-]", " ", text.lower())
    words = set(normalized.split())
    hits = len(words & terms)
    return round(min(1.0, hits / 6.0), 3)


def recency_score(date_value: str | None) -> float:
    """Decay recentness over 30 days; unknown dates get a neutral low score."""
    dt = parse_datetime(date_value)
    if not dt:
        return 0.35
    age_days = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400)
    return round(math.exp(-age_days / 18.0), 3)


def source_quality(source_name: str) -> float:
    """Favor primary or technical sources slightly over aggregation."""
    source = source_name.lower()
    if any(x in source for x in ["openai", "anthropic", "huggingface", "deepmind", "microsoft", "arxiv"]):
        return 1.0
    if "hacker news" in source:
        return 0.55
    return 0.4
