"""Research sufficiency and expansion agents.

This module answers the question the previous version of the package did not
answer well enough:

    "Do we have enough evidence to write a compelling, current editorial?"

A production content agent should not draft from one scraped page just because a
topic was selected.  It needs a bounded research loop that can inspect its own
evidence, decide what is missing, and gather more material before spending
tokens on article generation.

The implementation is intentionally deterministic.  The LLM is expensive and
less auditable for this stage.  Python can cheaply check source count, authority,
relevance, recency, and excerpt volume before the writer model is called.
"""

from __future__ import annotations

import re
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from bs4 import BeautifulSoup

from .schemas import (
    AgentConfig,
    CandidateTopic,
    ResearchEvidence,
    ResearchSufficiencyReport,
    SourceItem,
)
from .scrapers import HttpClient, clean_text, parse_datetime
from .similarity import jaccard, tokens
from .token_budget import clean_for_prompt
from .source_diversity import evaluate_source_diversity


# Domains with primary-source or high-trust relevance for AI/business/engineering
# topics.  This is not an endorsement list; it is an operational hint that
# official documentation, research labs, standards bodies, and credible
# engineering sources are more useful than anonymous aggregation.
AUTHORITY_DOMAIN_HINTS = {
    "openai.com": 1.0,
    "anthropic.com": 1.0,
    "huggingface.co": 1.0,
    "deepmind.google": 1.0,
    "ai.google": 1.0,
    "microsoft.com": 0.9,
    "github.com": 0.75,
    "modelcontextprotocol.io": 1.0,
    "nist.gov": 1.0,
    "owasp.org": 0.9,
    "arxiv.org": 0.85,
    "langchain.com": 0.75,
    "developers.google.com": 0.85,
}


@dataclass
class ResearchPlan:
    """Small record describing what the research agent intends to add."""

    round_number: int
    planned_urls: list[str]
    reason: str


class ResearchAgent:
    """Gather and evaluate enough research evidence before drafting.

    This class acts like a specialized sub-agent.  It does not write prose.  It
    owns the research sufficiency decision and produces a compact evidence set
    that can be safely injected into later prompts.
    """

    def __init__(
        self,
        config: AgentConfig,
        http: HttpClient,
        emit: Callable[[str, dict | None], object],
    ) -> None:
        self.config = config
        self.http = http
        self.emit = emit

    def gather(
        self,
        selected: CandidateTopic,
        source_items: list[SourceItem],
    ) -> tuple[list[ResearchEvidence], ResearchSufficiencyReport]:
        """Return evidence and a final sufficiency report.

        The loop is bounded by config.research_max_rounds.  Each round evaluates
        the current evidence, then adds the most relevant missing sources if the
        evidence is still thin.  The writer model is not called until this loop
        finishes.
        """

        evidence: list[ResearchEvidence] = []
        actions_taken: list[str] = []

        # Round 0 always fetches the selected candidate source.
        self.emit("research_initial_source_start", {"url": selected.url})
        selected_evidence = self._evidence_from_source_item(
            SourceItem(
                title=selected.title,
                url=selected.url,
                source_name=selected.source_name,
                published=selected.published,
                summary=selected.summary,
            ),
            selected_seed=selected,
            reason="selected_candidate",
        )
        evidence.append(selected_evidence)
        actions_taken.append(f"Fetched selected candidate source: {selected.url}")
        self.emit(
            "research_initial_source_end",
            {"chars": selected_evidence.chars, "authority": selected_evidence.authority_score},
        )

        final_report = self.evaluate(evidence, selected, actions_taken, rounds_completed=0)

        for round_number in range(1, self.config.research_max_rounds + 1):
            if final_report.sufficient:
                break

            self.emit(
                "research_sufficiency_insufficient",
                {
                    "round": round_number - 1,
                    "score": final_report.score,
                    "issues": final_report.issues,
                },
            )

            plan = self.plan_additional_research(selected, source_items, evidence, round_number)
            self.emit(
                "research_expansion_plan",
                {
                    "round": plan.round_number,
                    "planned_urls": plan.planned_urls,
                    "reason": plan.reason,
                },
            )

            if not plan.planned_urls:
                actions_taken.append("No additional sources available for expansion.")
                final_report = self.evaluate(evidence, selected, actions_taken, round_number)
                break

            added_this_round = 0
            for item in self._items_for_urls(plan.planned_urls, source_items, selected):
                if len(evidence) >= self.config.research_max_evidence_items:
                    break
                if any(existing.url == item.url for existing in evidence):
                    continue
                ev = self._evidence_from_source_item(item, selected_seed=selected, reason="research_expansion")
                if ev.chars < 120:
                    actions_taken.append(f"Skipped very thin source: {item.url}")
                    continue
                evidence.append(ev)
                added_this_round += 1
                actions_taken.append(f"Added research source: {item.url}")

            self.emit(
                "research_expansion_end",
                {"round": round_number, "added": added_this_round, "evidence_count": len(evidence)},
            )

            final_report = self.evaluate(evidence, selected, actions_taken, round_number)

        self.emit(
            "research_sufficiency_end",
            {
                "sufficient": final_report.sufficient,
                "score": final_report.score,
                "issues": final_report.issues,
                "evidence_count": final_report.evidence_count,
                "authoritative_count": final_report.authoritative_count,
                "total_excerpt_chars": final_report.total_excerpt_chars,
                "rounds_completed": final_report.rounds_completed,
            },
        )
        return evidence, final_report

    def evaluate(
        self,
        evidence: list[ResearchEvidence],
        selected: CandidateTopic,
        actions_taken: list[str],
        rounds_completed: int,
    ) -> ResearchSufficiencyReport:
        """Score the current evidence set and explain any gaps.

        A source set is considered sufficient only when it is diverse enough,
        authoritative enough, long enough, and relevant enough to support an
        article that is more than a shallow trend summary.
        """

        usable = [ev for ev in evidence if ev.chars >= 120]
        total_chars = sum(ev.chars for ev in usable)
        authoritative = [ev for ev in usable if ev.authority_score >= 0.75]
        relevant = [ev for ev in usable if ev.relevance_score >= 0.05 or ev.authority_score >= 0.75 or ev.url == selected.url]
        domains = {domain_from_url(ev.url) for ev in usable}
        diversity_report = evaluate_source_diversity(usable, min_categories=3)

        issues: list[str] = []
        if len(usable) < self.config.research_min_sources:
            issues.append(
                f"Need at least {self.config.research_min_sources} usable sources; have {len(usable)}."
            )
        if len(authoritative) < self.config.research_min_authoritative_sources:
            issues.append(
                "Need more authoritative/primary sources for factual grounding."
            )
        if total_chars < self.config.research_min_total_chars:
            issues.append(
                f"Need more source text; have {total_chars} chars, target {self.config.research_min_total_chars}."
            )
        if len(relevant) < max(2, min(4, self.config.research_min_sources - 1)):
            issues.append("Need more sources that overlap with the selected topic.")
        if len(domains) < 3 and len(usable) >= 3:
            issues.append("Need more source diversity; too many sources are from one domain.")
        # Source-type diversity is stricter than domain diversity. It asks for
        # different kinds of evidence: official/platform, standards/research,
        # engineering docs, and credible reporting where available.
        issues.extend(diversity_report.issues)

        # Simple weighted score.  This is useful for trace comparison between
        # runs and tells the operator whether expansion is improving research.
        source_score = min(1.0, len(usable) / max(1, self.config.research_min_sources))
        auth_score = min(1.0, len(authoritative) / max(1, self.config.research_min_authoritative_sources))
        char_score = min(1.0, total_chars / max(1, self.config.research_min_total_chars))
        relevance_score = min(1.0, len(relevant) / max(1, self.config.research_min_sources))
        diversity_score = min(1.0, (len(domains) / 3.0) * 0.5 + diversity_report.score * 0.5)
        score = round(
            0.24 * source_score
            + 0.24 * auth_score
            + 0.22 * char_score
            + 0.20 * relevance_score
            + 0.10 * diversity_score,
            3,
        )

        return ResearchSufficiencyReport(
            sufficient=not issues,
            score=score,
            issues=issues,
            actions_taken=list(actions_taken),
            evidence_count=len(usable),
            authoritative_count=len(authoritative),
            total_excerpt_chars=total_chars,
            rounds_completed=rounds_completed,
            source_diversity=diversity_report.to_dict(),
        )

    def plan_additional_research(
        self,
        selected: CandidateTopic,
        source_items: list[SourceItem],
        evidence: list[ResearchEvidence],
        round_number: int,
    ) -> ResearchPlan:
        """Choose additional URLs using related discovered items and curated sources."""

        existing_urls = {ev.url for ev in evidence}
        planned: list[str] = []

        # 1. Prefer newly discovered recent sources that overlap with the
        # selected topic.  This keeps the article timely.
        related = sorted(
            (item for item in source_items if item.url not in existing_urls),
            key=lambda item: relatedness(selected, item),
            reverse=True,
        )
        for item in related:
            if len(planned) >= 3:
                break
            if relatedness(selected, item) >= 0.05:
                planned.append(item.url)

        # 2. Fill with curated background sources for depth and implementation
        # credibility.  The writer prompt will still cite only sources it uses.
        for item in curated_background_sources(selected):
            if len(planned) >= 5:
                break
            if item.url not in existing_urls and item.url not in planned:
                planned.append(item.url)

        return ResearchPlan(
            round_number=round_number,
            planned_urls=planned,
            reason="Evidence gate requested more relevant, authoritative, or diverse sources.",
        )

    def _items_for_urls(
        self,
        urls: list[str],
        source_items: list[SourceItem],
        selected: CandidateTopic,
    ) -> list[SourceItem]:
        """Resolve planned URLs to SourceItem records.

        URLs from live scouting retain their title/summary/date.  Curated URLs
        are resolved from curated_background_sources().
        """

        by_url = {item.url: item for item in source_items}
        by_url.update({item.url: item for item in curated_background_sources(selected)})
        out: list[SourceItem] = []
        for url in urls:
            item = by_url.get(url)
            if item is None:
                item = SourceItem(title=url, url=url, source_name=domain_from_url(url))
            out.append(item)
        return out

    def _evidence_from_source_item(
        self,
        item: SourceItem,
        selected_seed: CandidateTopic,
        reason: str,
    ) -> ResearchEvidence:
        """Fetch/clean one source and compute authority/relevance metadata."""

        if self.config.offline:
            excerpt = offline_excerpt_for(item, selected_seed)
        else:
            excerpt = fetch_source_excerpt(self.http, item.url, fallback=item.summary)

        excerpt = clean_for_prompt(excerpt)
        authority = source_authority_score(item.url, item.source_name)
        relevance = relatedness(selected_seed, item)

        return ResearchEvidence(
            title=item.title or item.url,
            url=item.url,
            source_name=item.source_name or domain_from_url(item.url),
            published=item.published,
            excerpt=excerpt[: max(self.config.research_per_source_chars * 3, 3000)],
            relevance_score=round(relevance, 3),
            authority_score=round(authority, 3),
            chars=len(excerpt),
            notes=[reason],
        )


def fetch_source_excerpt(http: HttpClient, url: str, fallback: str = "") -> str:
    """Fetch a URL and return cleaned page text.

    All web text is treated as untrusted evidence.  The caller decides how much
    of it to inject into prompts after compression.
    """

    # Retry logic with exponential backoff
    max_retries = 3
    for attempt in range(max_retries):
        try:
            html = http.get_text(url)
            break  # Success, break out of retry loop
        except Exception:
            if attempt == max_retries - 1:  # Last attempt
                return fallback
            else:
                # Exponential backoff
                time.sleep(2 ** attempt)

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "form", "aside"]):
        tag.decompose()
    text = clean_text(soup.get_text(" ", strip=True))
    return text or fallback


def source_authority_score(url: str, source_name: str = "") -> float:
    """Score whether a source looks primary/official/technically credible."""

    combined = f"{url} {source_name}".lower()
    for domain, score in AUTHORITY_DOMAIN_HINTS.items():
        if domain in combined:
            return score
    if "news.ycombinator.com" in combined or "hacker news" in combined:
        return 0.45
    if "medium.com" in combined or "substack.com" in combined:
        return 0.35
    return 0.50


def relatedness(selected: CandidateTopic, item: SourceItem | ResearchEvidence) -> float:
    """Compute rough textual overlap between the selected topic and another item."""

    selected_text = f"{selected.title} {selected.summary}"
    other_summary = getattr(item, "summary", "") or getattr(item, "excerpt", "")
    other_text = f"{item.title} {other_summary}"
    return jaccard(tokens(selected_text), tokens(other_text))


def domain_from_url(url: str) -> str:
    """Extract a stable lowercase domain from a URL."""

    try:
        return urllib.parse.urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def curated_background_sources(selected: CandidateTopic) -> list[SourceItem]:
    """Return topic-aware background sources for depth.

    These sources are not substitutes for recent topic discovery.  They provide
    official documentation, standards, or engineering context the article can use
    when explaining implementation reality.
    """

    text = f"{selected.title} {selected.summary}".lower()
    items: list[SourceItem] = []

    if any(term in text for term in ["agent", "workflow", "tool", "memory", "mcp", "context"]):
        items.extend(
            [
                SourceItem(
                    "OpenAI Agents documentation",
                    "https://developers.openai.com/api/docs/guides/agents",
                    "OpenAI documentation",
                    None,
                    "Official documentation about agents, tools, handoffs, guardrails, and workflow orchestration.",
                ),
                SourceItem(
                    "Model Context Protocol introduction",
                    "https://modelcontextprotocol.io/introduction",
                    "Model Context Protocol",
                    None,
                    "MCP describes a standard way for AI applications to connect to tools, resources, and prompts.",
                ),
                SourceItem(
                    "LangGraph durable execution concepts",
                    "https://docs.langchain.com/oss/python/langgraph/durable-execution",
                    "LangChain documentation",
                    None,
                    "Durable execution guidance for checkpointed agent workflows.",
                ),
            ]
        )

    if any(term in text for term in ["risk", "safety", "governance", "security", "prompt", "reliability"]):
        items.extend(
            [
                SourceItem(
                    "OWASP Top 10 for LLM Applications",
                    "https://owasp.org/www-project-top-10-for-large-language-model-applications/",
                    "OWASP",
                    None,
                    "Security risk categories for large language model applications.",
                ),
                SourceItem(
                    "NIST AI Risk Management Framework",
                    "https://www.nist.gov/itl/ai-risk-management-framework",
                    "NIST",
                    None,
                    "A risk management framework for artificial intelligence systems.",
                ),
            ]
        )

    if any(term in text for term in ["model", "inference", "hugging", "open-weight", "image", "multimodal"]):
        items.extend(
            [
                SourceItem(
                    "Hugging Face Inference Providers documentation",
                    "https://huggingface.co/docs/inference-providers/en/index",
                    "Hugging Face documentation",
                    None,
                    "Unified hosted inference for many model providers.",
                ),
                SourceItem(
                    "Hugging Face structured output guide",
                    "https://huggingface.co/docs/inference-providers/guides/structured-output",
                    "Hugging Face documentation",
                    None,
                    "Structured outputs for reliable, parsable model responses.",
                ),
            ]
        )

    # Always include search essentials because the final artifact is intended to
    # be SEO-friendly and the user's prompt explicitly asks the article to adhere
    # to Google's essentials.  The article generator can cite it only if used.
    items.append(
        SourceItem(
            "Google Search Essentials",
            "https://developers.google.com/search/docs/essentials",
            "Google Search Central",
            None,
            "Official guidance on creating content eligible for Google Search.",
        )
    )

    # Deduplicate curated sources while preserving order.
    seen: set[str] = set()
    deduped: list[SourceItem] = []
    for item in items:
        if item.url not in seen:
            seen.add(item.url)
            deduped.append(item)
    return deduped


def offline_excerpt_for(item: SourceItem, selected: CandidateTopic) -> str:
    """Provide deterministic evidence text for offline tests and demos."""

    base = item.summary or (
        f"{item.title} is used as source evidence for an article connected to {selected.title}."
    )
    authority_note = (
        "This offline fixture represents a reputable source used to explain implementation reality, "
        "business consequences, and technical constraints without making live network calls."
    )
    repeated_context = (
        "The evidence emphasizes practical AI editorial concerns: workflow boundaries, source verification, "
        "tool control, retrieval discipline, memory management, evaluation, human review, cost, latency, "
        "governance, and clear business purpose. "
    )
    return f"{base} {authority_note} {repeated_context * 8}"
