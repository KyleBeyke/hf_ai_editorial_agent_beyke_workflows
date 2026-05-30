"""Final article-package review and revision prompting.

The first package version only checked whether required Markdown sections were
present.  That is necessary but not enough.  This module adds a second gate that
looks for truthfulness, clarity, and purpose problems before delivery.

Important limitation: no deterministic checker can prove that a long editorial is
fully true.  What this reviewer *can* do is catch common automation failures:
invented internal links, sources that were not in the collected evidence, missing
source grounding, placeholder artifacts, unclear purpose, generic article shape,
and obvious overclaiming language.
"""

from __future__ import annotations

import re

from .schemas import CandidateTopic, EditorialReview, ResearchEvidence, SiteArticle
from .site_profile import normalize_domain
from .validation import ValidationResult, extract_article_body, extract_section
from .claim_ledger import build_claim_ledger, ledger_needs_revision
from .style_review import review_style


URL_RE = re.compile(r"https?://[^\s)`>\]]+")


class EditorialPackageReviewer:
    """Review the final package from the perspective of a cautious editor."""

    def review(
        self,
        markdown: str,
        *,
        selected: CandidateTopic,
        evidence: list[ResearchEvidence],
        site_articles: list[SiteArticle],
        validation: ValidationResult,
    ) -> EditorialReview:
        """Return a structured review across truthfulness, clarity, and purpose."""

        truthfulness: list[str] = []
        clarity: list[str] = []
        purpose: list[str] = []

        # Start with formal validation failures so the revision editor sees one
        # consolidated list rather than separate checker outputs.
        for issue in validation.issues:
            clarity.append(f"Package validation issue: {issue}")

        evidence_urls = normalize_url_set([ev.url for ev in evidence])
        selected_url = normalize_url(selected.url)
        verified_internal_urls = normalize_url_set([a.url for a in site_articles])
        internal_domains = {normalize_domain(a.url) for a in site_articles if a.url}
        internal_domains.update({"beykeworkflows.com"})

        source_section = extract_all_heading_sections(markdown, "Sources")
        related_section = (
            extract_all_heading_sections(markdown, "Related articles from Beyke Workflows")
        )
        article_body = extract_article_body(markdown)
        focus_keyword = validation.focus_keyword or ""

        if selected_url and selected_url not in normalize_url_set(URL_RE.findall(source_section)):
            truthfulness.append("Sources section should include the selected candidate source URL.")

        # Check external source URLs against the evidence bundle.  The article
        # generation prompt asks the model not to invent sources; this enforces it.
        for url in URL_RE.findall(source_section):
            norm = normalize_url(url)
            if norm and norm not in evidence_urls and not url_domain_is_internal(url, internal_domains):
                truthfulness.append(f"Unverified external source listed: {url}")

        # Check internal links against the live archive scrape/fixture.
        for url in URL_RE.findall(related_section):
            norm = normalize_url(url)
            if url_domain_is_internal(url, internal_domains) and norm not in verified_internal_urls:
                truthfulness.append(f"Unverified or non-archive internal related link: {url}")

        if not source_section.strip():
            truthfulness.append("Sources section is missing or empty.")
        if not related_section.strip():
            truthfulness.append("Related articles section is missing or empty.")

        # Overconfident phrases are not automatically false, but they deserve a
        # revision instruction unless the article carefully supports them.
        risky_phrases = [
            "guarantees",
            "guaranteed",
            "always works",
            "never fails",
            "fully autonomous without oversight",
            "proves production readiness",
            "best model for every",
        ]
        lower = markdown.lower()
        for phrase in risky_phrases:
            if phrase in {"guarantees", "guaranteed"}:
                for hit in re.finditer(rf"\b{re.escape(phrase)}\b", lower):
                    sentence_start = max(lower.rfind(".", 0, hit.start()), lower.rfind("\n", 0, hit.start()))
                    sentence = lower[sentence_start + 1 : lower.find(".", hit.end()) if "." in lower[hit.end():] else len(lower)]
                    if "does not" not in sentence and "do not" not in sentence and "without guarantee" not in sentence:
                        truthfulness.append(f"Potentially overbroad claim needs qualification: '{phrase}'")
                        break
            elif phrase in lower:
                truthfulness.append(f"Potentially overbroad claim needs qualification: '{phrase}'")

        # Claim-ledger review catches factual-looking statements that do not
        # match collected evidence. It is a conservative audit signal rather
        # than a proof of truth.
        ledger = build_claim_ledger(markdown, evidence)
        truthfulness.extend(ledger_needs_revision(ledger))

        # Style review catches generic AI/corporate prose that weakens the
        # editorial voice and violates the user's prompt requirements.
        style_report = review_style(markdown)
        clarity.extend(style_report.issues)

        # Clarity checks focus on reader usefulness rather than grammar.
        if len(article_body.splitlines()) < 12:
            clarity.append("Article body appears too thin or poorly structured.")
        if has_huge_paragraph(article_body, word_limit=260):
            clarity.append("One or more paragraphs are too long for web readability.")
        if "In today's rapidly evolving" in markdown or "Artificial intelligence is transforming" in markdown:
            clarity.append("Opening contains a generic AI-intro phrase the prompt asks to avoid.")

        # Purpose checks make sure the editorial is doing the requested job.
        if focus_keyword and focus_keyword.lower() not in article_body.lower():
            purpose.append("Focus keyword does not appear naturally in the article body.")
        if not re.search(r"\bbusiness\b|\bleaders\b|\bdecision makers\b", article_body, re.I):
            purpose.append("Business audience is not clearly addressed.")
        if not re.search(r"\bengineers?\b|\bdevelopers?\b|\btechnical\b|\bimplementation\b", article_body, re.I):
            purpose.append("Technical audience is not clearly addressed.")
        if not re.search(r"\bthesis\b|\bargument\b|\bthe point\b|\bthe mistake\b", article_body, re.I):
            purpose.append("Editorial thesis/argument is not explicit enough.")
        if re.search(r"^###\s*Exercise\b|\bstudents should\b|\bthis lesson\b", markdown, re.I | re.M):
            purpose.append("Article appears to drift into lesson-module language.")

        instructions: list[str] = []
        if truthfulness:
            instructions.append("Fix truthfulness/source-grounding issues: " + "; ".join(truthfulness))
        if clarity:
            instructions.append("Fix clarity/readability issues: " + "; ".join(clarity))
        if purpose:
            instructions.append("Fix purpose/audience/editorial-positioning issues: " + "; ".join(purpose))

        return EditorialReview(
            ok=not (truthfulness or clarity or purpose),
            truthfulness_issues=truthfulness,
            clarity_issues=clarity,
            purpose_issues=purpose,
            revision_required=bool(truthfulness or clarity or purpose),
            revision_instructions=instructions,
        )


def build_review_repair_prompt(
    *,
    article_md: str,
    review: EditorialReview,
    evidence: list[ResearchEvidence],
    selected: CandidateTopic,
    verified_internal_links: list[SiteArticle],
) -> str:
    """Build a bounded repair prompt for the revision agent.

    The prompt includes the full article because the revision agent must return a
    complete WordPress-ready package.  Evidence is included as an inventory rather
    than raw page dumps to limit token use.
    """

    evidence_inventory = "\n".join(
        f"- {ev.title}: {ev.url} (source={ev.source_name}, authority={ev.authority_score:.2f})"
        for ev in evidence
    )
    internal_inventory = "\n".join(f"- {a.title}: {a.url}" for a in verified_internal_links)
    instructions = "\n".join(f"- {x}" for x in review.revision_instructions)

    return f"""\
You are the revision editor for a WordPress-ready editorial article package.

The package below failed final review. Revise it in place and return the complete
corrected package only. Preserve the required section order. Do not invent new
sources, internal links, APIs, benchmarks, statistics, or URLs.

Selected topic source:
- {selected.title}: {selected.url}

Allowed external source inventory:
{evidence_inventory}

Verified internal related-link inventory:
{internal_inventory}

Required fixes:
{instructions}

Return the corrected article package only.

ARTICLE PACKAGE TO REVISE:
{article_md}
"""


def normalize_url(url: str) -> str:
    """Normalize URLs enough for source-set comparison."""

    url = url.strip().rstrip(".,;")
    try:
        # Avoid importing urlparse twice in the hot path unless needed.
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        return urlunparse((parsed.scheme.lower(), parsed.netloc.lower().replace("www.", ""), path, "", "", ""))
    except (ValueError, AttributeError):
        return url.lower().rstrip("/")


def normalize_url_set(urls: list[str]) -> set[str]:
    """Normalize a list of URLs into a comparable set."""

    return {normalize_url(url) for url in urls if url}




def extract_all_heading_sections(markdown: str, heading: str) -> str:
    """Extract and concatenate every level-2/level-3 section with this heading.

    A malformed model response can accidentally duplicate sections.  Reviewing
    all occurrences prevents a later bad section from hiding behind an earlier
    valid one.
    """

    sections: list[str] = []
    for level in (3, 2):
        pattern = rf"^{('#' * level)}\s+{re.escape(heading)}\s*$"
        for match in re.finditer(pattern, markdown, flags=re.MULTILINE):
            start = match.end()
            next_match = re.search(rf"^#{{1,{level}}}\s+", markdown[start:], flags=re.MULTILINE)
            end = start + next_match.start() if next_match else len(markdown)
            sections.append(markdown[start:end].strip())
    return "\n\n".join(section for section in sections if section)


def extract_any_heading_section(markdown: str, heading: str) -> str:
    """Extract content under either a level-2 or level-3 heading.

    The user's article prompt places Sources and Related Articles inside the
    consolidated WordPress content block as level-3 headings, while some package
    formats may use level-2 headings.  The reviewer accepts both.
    """

    for level in (3, 2):
        pattern = rf"^{('#' * level)}\s+{re.escape(heading)}\s*$"
        match = re.search(pattern, markdown, flags=re.MULTILINE)
        if not match:
            continue
        start = match.end()
        next_match = re.search(rf"^#{{1,{level}}}\s+", markdown[start:], flags=re.MULTILINE)
        end = start + next_match.start() if next_match else len(markdown)
        return markdown[start:end].strip()
    return ""

def has_huge_paragraph(text: str, word_limit: int) -> bool:
    """Detect paragraphs that are too long for comfortable editorial reading."""

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    for para in paragraphs:
        if len(re.findall(r"\b[\w'-]+\b", para)) > word_limit:
            return True
    return False


def url_domain_is_internal(url: str, internal_domains: set[str]) -> bool:
    """Return True when URL belongs to configured publication domains."""

    return normalize_domain(url) in {normalize_domain(d) for d in internal_domains if d}
