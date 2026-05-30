"""Full-body duplicate detection against existing beykeworkflows.com articles.

Title/excerpt checks are useful for topic selection, but they can miss an article
that is phrased differently while making the same argument. This module fetches
existing article bodies where possible and compares them to the generated article
body. The result is an editorial risk signal, not a copyright verdict.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from difflib import SequenceMatcher
from bs4 import BeautifulSoup

from .schemas import SiteArticle
from .scrapers import HttpClient, clean_text
from .similarity import tokens, jaccard, normalize
from .validation import extract_article_body


@dataclass
class BodyDuplicateRecord:
    title: str
    url: str
    token_overlap: float
    sequence_similarity: float
    risk: float
    reason: str


@dataclass
class BodyDuplicateReport:
    ok: bool
    max_risk: float
    records: list[BodyDuplicateRecord]
    issues: list[str]

    def to_dict(self) -> dict:
        data = asdict(self)
        return data


def fetch_article_body(http: HttpClient, article: SiteArticle) -> str:
    """Fetch and clean one published article body, falling back to archive excerpt."""

    # Retry logic with exponential backoff
    max_retries = 3
    for attempt in range(max_retries):
        try:
            html = http.get_text(article.url)
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "form", "aside"]):
                tag.decompose()
            # WordPress themes usually use <article>, but fall back gracefully.
            node = soup.find("article") or soup.find("main") or soup
            result = clean_text(node.get_text(" ", strip=True)) or article.excerpt
            return result
        except Exception:
            if attempt == max_retries - 1:  # Last attempt
                return article.excerpt
            else:
                # Exponential backoff
                time.sleep(2 ** attempt)


def compare_body_to_existing(article_md: str, existing: list[SiteArticle], http: HttpClient | None = None, *, offline: bool = False, max_articles: int = 20) -> BodyDuplicateReport:
    """Compare generated article body against existing article bodies."""

    body = extract_article_body(article_md) or article_md
    body_norm = normalize(body)
    body_tokens = tokens(body_norm)
    records: list[BodyDuplicateRecord] = []

    for site_article in existing[:max_articles]:
        existing_body = site_article.excerpt if offline or http is None else fetch_article_body(http, site_article)
        overlap = jaccard(body_tokens, tokens(existing_body))
        seq = SequenceMatcher(None, body_norm[:5000], normalize(existing_body)[:5000]).ratio()
        risk = round(max(overlap, seq * 0.75), 3)
        reason = "low overlap"
        if risk >= 0.62:
            reason = "high body/thesis overlap risk"
        elif risk >= 0.45:
            reason = "moderate body/thesis overlap risk"
        records.append(
            BodyDuplicateRecord(
                title=site_article.title,
                url=site_article.url,
                token_overlap=round(overlap, 3),
                sequence_similarity=round(seq, 3),
                risk=risk,
                reason=reason,
            )
        )

    records.sort(key=lambda r: r.risk, reverse=True)
    max_risk = records[0].risk if records else 0.0
    issues = []
    if max_risk >= 0.62:
        issues.append("Generated article has high full-body similarity to an existing beykeworkflows.com article.")
    elif max_risk >= 0.45:
        issues.append("Generated article has moderate full-body similarity; human editor should verify novelty.")

    return BodyDuplicateReport(ok=max_risk < 0.62, max_risk=max_risk, records=records, issues=issues)


def write_duplicate_report(report: BodyDuplicateReport, path: Path) -> None:
    """Persist full-body duplicate report as JSON."""

    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
