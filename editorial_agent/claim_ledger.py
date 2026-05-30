"""Claim ledger and fact/analysis boundary generation.

A final editorial can be truthful and still contain interpretation. The problem
is when a model presents unsourced interpretation as fact. This module builds an
audit artifact that separates:

- source-backed factual claims;
- editorial analysis and recommendations;
- claims that deserve human review before publication.

The ledger is not a formal proof system. It is a practical safeguard that gives
the human editor a clear list of what the agent believes it said and why.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.parse import urlparse

from .schemas import ResearchEvidence
from .validation import extract_article_body


@dataclass
class ClaimRecord:
    """One claim-like sentence from the generated article."""

    claim: str
    classification: str
    support_url: str | None
    support_name: str | None
    confidence: str
    reason: str


def source_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except (ValueError, AttributeError):
        return ""


def sentence_split(text: str) -> list[str]:
    """Split prose into sentence-ish records without adding an NLP dependency."""

    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", re.sub(r"\s+", " ", text).strip())
    return [p.strip() for p in parts if len(p.split()) >= 6]


def source_terms(ev: ResearchEvidence) -> set[str]:
    """Extract lightweight terms used to match a claim to an evidence item."""

    text = f"{ev.title} {ev.source_name} {source_domain(ev.url)}"
    return {t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", text)}


def classify_claim(sentence: str, evidence: list[ResearchEvidence]) -> ClaimRecord:
    """Classify a sentence as factual, analytical, recommendation, or review-needed."""

    lower = sentence.lower()

    recommendation_markers = [
        "should", "need to", "needs to", "better", "leaders should", "teams should",
        "the better question", "the right question", "the point is", "the mistake",
    ]
    if any(marker in lower for marker in recommendation_markers):
        return ClaimRecord(sentence, "editorial_recommendation", None, None, "medium", "Normative guidance rather than a directly source-cited fact.")

    # Match source names, domains, and title terms to the sentence.
    best_ev: ResearchEvidence | None = None
    best_score = 0
    claim_terms = {t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", sentence)}
    for ev in evidence:
        overlap = len(claim_terms & source_terms(ev))
        if overlap > best_score:
            best_score = overlap
            best_ev = ev

    factual_markers = [
        "documentation", "official", "published", "released", "announced",
        "states", "describes", "supports", "requires", "allows", "provides",
        "framework", "standard", "research", "study", "report", "api",
    ]
    has_number = bool(re.search(r"\b\d{4}\b|\b\d+[%x]?\b", sentence))
    looks_factual = has_number or any(marker in lower for marker in factual_markers)

    if best_ev and best_score >= 1:
        return ClaimRecord(sentence, "source_supported_fact", best_ev.url, best_ev.source_name, "medium", "Sentence overlaps with collected evidence inventory.")

    if looks_factual:
        return ClaimRecord(sentence, "needs_source_review", None, None, "low", "Sentence looks factual but was not matched to a collected source.")

    return ClaimRecord(sentence, "editorial_analysis", None, None, "medium", "Analytical synthesis or framing, not a direct factual citation.")


def build_claim_ledger(markdown: str, evidence: list[ResearchEvidence]) -> list[ClaimRecord]:
    """Create a claim ledger from the final article body."""

    body = extract_article_body(markdown) or markdown
    return [classify_claim(sentence, evidence) for sentence in sentence_split(body)]


def write_claim_artifacts(markdown: str, evidence: list[ResearchEvidence], out_dir: Path) -> tuple[Path, Path]:
    """Write JSON and Markdown audit artifacts for the human editor."""

    ledger = build_claim_ledger(markdown, evidence)
    json_path = out_dir / "claim_ledger.json"
    md_path = out_dir / "fact_analysis_boundary.md"

    json_path.write_text(
        json.dumps([asdict(record) for record in ledger], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    grouped: dict[str, list[ClaimRecord]] = {}
    for record in ledger:
        grouped.setdefault(record.classification, []).append(record)

    lines = [
        "# Fact / Analysis Boundary",
        "",
        "This file is for editorial review. It is not meant to be pasted into WordPress.",
        "",
    ]
    for section in [
        "source_supported_fact",
        "needs_source_review",
        "editorial_analysis",
        "editorial_recommendation",
    ]:
        records = grouped.get(section, [])
        lines.append(f"## {section.replace('_', ' ').title()}")
        if not records:
            lines.append("- None.")
        for record in records[:80]:
            support = f" Supported by: {record.support_name} — {record.support_url}" if record.support_url else ""
            lines.append(f"- {record.claim}{support}")
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def ledger_needs_revision(ledger: list[ClaimRecord], *, max_review_needed: int = 8) -> list[str]:
    """Return review issues if too many factual-looking claims lack support."""

    needs_review = [r for r in ledger if r.classification == "needs_source_review"]
    if len(needs_review) > max_review_needed:
        return [f"Claim ledger has {len(needs_review)} factual-looking claims without matched source support."]
    return []
