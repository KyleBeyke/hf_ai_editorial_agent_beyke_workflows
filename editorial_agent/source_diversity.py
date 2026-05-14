"""Source diversity scoring for the research sufficiency gate.

The research loop should not only count sources. Five posts from the same vendor
can still produce a weak editorial because they share the same incentives and
blind spots. This module classifies each evidence item into a coarse source type
so the research gate can require a healthier mix before drafting.

The categories are intentionally simple and deterministic. They are not a moral
ranking of sources; they are an operational safeguard against shallow evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from urllib.parse import urlparse

from .schemas import ResearchEvidence


@dataclass
class SourceDiversityReport:
    """Machine-readable explanation of source mix quality."""

    categories: dict[str, int]
    unique_domains: int
    score: float
    issues: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


OFFICIAL_AI_DOMAINS = {
    "openai.com",
    "anthropic.com",
    "huggingface.co",
    "deepmind.google",
    "ai.google",
    "microsoft.com",
    "aws.amazon.com",
    "cloud.google.com",
    "developer.nvidia.com",
}

STANDARDS_SECURITY_DOMAINS = {
    "nist.gov",
    "owasp.org",
    "iso.org",
    "csrc.nist.gov",
}

RESEARCH_DOMAINS = {
    "arxiv.org",
    "nature.com",
    "science.org",
    "acm.org",
    "ieee.org",
}

ENGINEERING_DOC_DOMAINS = {
    "github.com",
    "docs.langchain.com",
    "langchain.com",
    "modelcontextprotocol.io",
    "developers.google.com",
    "developer.wordpress.org",
}

BUSINESS_TECH_MEDIA_DOMAINS = {
    "technologyreview.com",
    "theverge.com",
    "venturebeat.com",
    "wired.com",
    "economist.com",
    "ft.com",
    "wsj.com",
    "reuters.com",
}


def domain(url: str) -> str:
    """Return a normalized domain suitable for coarse classification."""

    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def classify_source(url: str, source_name: str = "") -> str:
    """Classify a source into a small set of editorially useful buckets."""

    d = domain(url)
    combined = f"{d} {source_name}".lower()

    if "beykeworkflows.com" in combined:
        return "verified_internal"
    if d in OFFICIAL_AI_DOMAINS or any(x in combined for x in ["documentation", "official"]):
        return "official_or_platform"
    if d in STANDARDS_SECURITY_DOMAINS:
        return "standards_security"
    if d in RESEARCH_DOMAINS:
        return "research"
    if d in ENGINEERING_DOC_DOMAINS:
        return "engineering_docs"
    if d in BUSINESS_TECH_MEDIA_DOMAINS or any(x in combined for x in ["reuters", "mit technology review"]):
        return "business_tech_media"
    if any(x in combined for x in ["medium.com", "substack", "hacker news", "reddit"]):
        return "community_or_commentary"
    return "other"


def evaluate_source_diversity(evidence: list[ResearchEvidence], *, min_categories: int = 3) -> SourceDiversityReport:
    """Measure whether the evidence set contains multiple useful source types."""

    categories: dict[str, int] = {}
    domains = set()
    for item in evidence:
        cat = classify_source(item.url, item.source_name)
        categories[cat] = categories.get(cat, 0) + 1
        domains.add(domain(item.url))

    useful_categories = {
        cat for cat in categories
        if cat not in {"community_or_commentary", "other"}
    }
    issues: list[str] = []
    if len(useful_categories) < min_categories:
        issues.append(
            f"Need more source-type diversity; have {len(useful_categories)} useful categories, target {min_categories}."
        )
    if categories.get("official_or_platform", 0) == 0:
        issues.append("Need at least one official/platform source when possible.")
    if categories.get("standards_security", 0) == 0 and categories.get("research", 0) == 0:
        issues.append("Need at least one standards, security, or research-oriented source when possible.")

    score = min(1.0, (len(useful_categories) / max(1, min_categories)) * 0.7 + (len(domains) / 3.0) * 0.3)
    return SourceDiversityReport(categories=categories, unique_domains=len(domains), score=round(score, 3), issues=issues)
