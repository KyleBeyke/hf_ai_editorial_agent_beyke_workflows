"""Duplicate and near-duplicate detection.

The goal is not to prove semantic novelty perfectly. The goal is to prevent the
agent from selecting a topic that is obviously already covered on beykeworkflows.com.

The implementation combines:

- normalized title comparison;
- token Jaccard overlap;
- difflib sequence similarity;
- keyword overlap with excerpts.

This is intentionally transparent. For editorial automation, explainable
duplicate checks are often more useful than opaque embedding scores.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Iterable

from .schemas import CandidateTopic, SiteArticle


STOPWORDS = {
    "a", "an", "the", "for", "to", "of", "and", "or", "in", "on", "with", "why",
    "how", "what", "is", "are", "be", "as", "at", "by", "from", "that", "this",
    "guide", "business", "ai", "llm", "llms", "smart", "powerful", "essential",
    "critical", "best", "hard", "lessons", "guide",
}


def normalize(text: str) -> str:
    """Normalize text for rough matching."""
    text = text.lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokens(text: str) -> set[str]:
    """Return meaningful tokens after normalization and stopword removal."""
    return {tok for tok in normalize(text).split() if tok and tok not in STOPWORDS and len(tok) > 2}


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    """Compute Jaccard overlap between two token sets."""
    aa = set(a)
    bb = set(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)


def similarity_ratio(a: str, b: str) -> float:
    """Sequence similarity after normalization."""
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def duplicate_risk(candidate: CandidateTopic, articles: list[SiteArticle]) -> tuple[float, str]:
    """Return the highest duplicate risk and a human-readable reason.

    Risk meaning:
    - >= 0.82: likely duplicate, should be excluded.
    - 0.65 to 0.82: partial duplicate, heavily penalize.
    - below 0.65: probably acceptable, but score can still be affected.
    """
    best_score = 0.0
    best_reason = "No close duplicate found."

    candidate_text = f"{candidate.title} {candidate.summary}"
    c_tokens = tokens(candidate_text)

    for article in articles:
        article_text = f"{article.title} {article.excerpt}"
        title_ratio = similarity_ratio(candidate.title, article.title)
        token_overlap = jaccard(c_tokens, tokens(article_text))
        excerpt_ratio = similarity_ratio(candidate.summary[:400], article.excerpt[:400])
        risk = max(title_ratio, token_overlap, excerpt_ratio * 0.85)

        if risk > best_score:
            best_score = risk
            best_reason = (
                f"Closest existing article: '{article.title}' "
                f"(title={title_ratio:.2f}, tokens={token_overlap:.2f}, excerpt={excerpt_ratio:.2f})"
            )

    return round(best_score, 3), best_reason
