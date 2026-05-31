"""Typed data contracts for the editorial agent.

This module is intentionally boring and explicit.  A maintainable agent should
move structured objects between stages instead of passing large anonymous
dictionaries everywhere.  The classes below are the "contracts" between the
research, planning, writing, review, and artifact-writing agents.

The project uses dataclasses rather than a heavier validation framework so the
example stays easy to read on Windows without extra dependencies.  In a larger
system, Pydantic models or JSON Schema contracts would be a natural upgrade.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .site_profile import DEFAULT_AUTHOR_NAME, DEFAULT_SITE_BASE_URL, DEFAULT_SITE_CATEGORY_URL, DEFAULT_SITE_NAME


def utc_now_iso() -> str:
    """Return a timezone-aware UTC timestamp in a stable JSON-friendly format."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class SourceItem:
    """A raw topic or article discovered from RSS, APIs, or public pages.

    SourceItem is intentionally lightweight.  At this stage the agent has only
    discovered a possible topic; it has not yet decided whether the source is
    useful, authoritative, recent enough, or novel relative to the configured publication site.
    """

    title: str
    url: str
    source_name: str
    published: str | None = None
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize this record for JSON artifacts and event payloads."""

        return asdict(self)


@dataclass
class SiteArticle:
    """A published site article used for duplication and linking."""

    title: str
    url: str
    date: str | None = None
    excerpt: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize this record for JSON artifacts and event payloads."""

        return asdict(self)


@dataclass
class CandidateTopic:
    """A normalized candidate topic with scoring and duplicate-check evidence.

    The candidate score is deterministic.  The LLM is not trusted to decide
    whether a topic is a duplicate or whether it is interesting enough without
    observable evidence.  That makes topic selection debuggable.
    """

    title: str
    url: str
    source_name: str
    published: str | None
    summary: str
    score: float = 0.0
    duplicate_risk: float = 0.0
    duplicate_reason: str = ""
    business_relevance: float = 0.0
    technical_relevance: float = 0.0
    recency_score: float = 0.0
    selected: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize this record for JSON artifacts and event payloads."""

        return asdict(self)


@dataclass
class ResearchEvidence:
    """A cleaned source excerpt that may be injected into the writing prompt.

    Evidence is separate from SourceItem because discovery and research are
    different stages.  A discovered topic might have no useful article text.
    A research item has actually been fetched, cleaned, scored, and budgeted for
    use by the article-generation prompt.
    """

    title: str
    url: str
    source_name: str
    published: str | None = None
    excerpt: str = ""
    relevance_score: float = 0.0
    authority_score: float = 0.0
    chars: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this record for JSON artifacts and event payloads."""

        return asdict(self)


@dataclass
class ResearchSufficiencyReport:
    """Decision record explaining whether the agent has enough evidence.

    This report is the research gate.  It prevents the writing agent from
    drafting from a thin single-source context when the topic needs deeper
    support.  The score is not a claim of truth; it is an operational check that
    the run has enough diverse evidence to attempt a useful article.
    """

    sufficient: bool
    score: float
    issues: list[str]
    actions_taken: list[str]
    evidence_count: int
    authoritative_count: int
    total_excerpt_chars: int
    rounds_completed: int
    source_diversity: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this report for JSON artifacts and event payloads."""

        return asdict(self)


@dataclass
class EditorialReview:
    """Final-package review across truthfulness, clarity, and purpose.

    This deterministic review does not prove every statement is true.  It checks
    whether the article is grounded in the collected evidence, uses verified
    internal links, avoids obvious placeholders, has an editorial purpose, and
    meets the package requirements.  If problems remain, the revision agent gets
    specific instructions instead of a vague "make it better" prompt.
    """

    ok: bool
    truthfulness_issues: list[str] = field(default_factory=list)
    clarity_issues: list[str] = field(default_factory=list)
    purpose_issues: list[str] = field(default_factory=list)
    revision_required: bool = False
    revision_instructions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this report for JSON artifacts and event payloads."""

        return asdict(self)


@dataclass
class AgentConfig:
    """Runtime configuration.

    The defaults are chosen so a Windows user can run one command after setting
    HF_TOKEN.  Offline mode is available for tests and dry runs.

    Token-budget fields use character counts instead of provider-specific token
    counters.  That keeps the package dependency-light.  The rough conversion is
    documented in token_budget.py.
    """

    site_category_url: str = DEFAULT_SITE_CATEGORY_URL
    site_base_url: str = DEFAULT_SITE_BASE_URL
    site_name: str = DEFAULT_SITE_NAME
    author_name: str = DEFAULT_AUTHOR_NAME
    output_dir: Path = Path("outputs")
    lookback_days: int = 21
    max_candidates: int = 25
    request_timeout_seconds: int = 20

    # Current practical HF text default.  Hugging Face provider availability can
    # change, so every model/provider can be overridden at the CLI or by env vars.
    hf_text_model: str = "openai/gpt-oss-120b:cheapest"
    hf_text_provider: str = "auto"

    # Image default prefers a high-quality professional image model.  The agent
    # can fall back to a deterministic local image so a run still produces a
    # WordPress-ready package when image inference fails.
    hf_image_model: str = "black-forest-labs/FLUX.1-Krea-dev:cheapest"
    hf_image_provider: str = "auto"

    offline: bool = False
    allow_offline_fallback: bool = True
    generate_image: bool = True
    user_agent: str = (
        "Mozilla/5.0 (compatible; HF-AI-Editorial-Agent/0.6; "
        f"+{DEFAULT_SITE_BASE_URL}/)"
    )

    # Research loop controls.  The agent may gather more evidence before
    # drafting if these thresholds are not met.
    research_min_sources: int = 5
    research_min_authoritative_sources: int = 2
    research_min_total_chars: int = 4500
    research_max_rounds: int = 3
    research_max_evidence_items: int = 8
    research_per_source_chars: int = 1800

    # Prompt/token optimization controls.  These are intentionally conservative
    # because long prompt templates are already provided by the user.
    max_internal_links_for_prompt: int = 8
    max_research_chars_for_topic_prompt: int = 7500
    max_research_chars_for_article_prompt: int = 9000
    max_topic_brief_tokens: int = 4500
    max_article_tokens: int = 10500
    max_revision_tokens: int = 10500

    # Final review and revision loop.  The revision loop is bounded so a bad
    # model response cannot burn unlimited tokens.
    enable_final_review: bool = True
    max_revision_passes: int = 2

    # Backward-compatible model lanes. These are still accepted by the CLI, but
    # the preferred configuration is now the per-stage `model_routes` mapping.
    # The lane values are used only when no routing file is provided.
    hf_small_text_model: str = "openai/gpt-oss-20b:cheapest"
    hf_small_text_provider: str = "auto"
    use_model_routing: bool = True

    # Per-stage model routing. Keys are stages such as "research_synthesis" or
    # "editorial_review"; values are dictionaries with model/provider/temperature.
    # Keeping this map in config makes model tuning auditable and avoids changing
    # the orchestration code every time a provider becomes faster, cheaper, or
    # less reliable.
    model_routes: dict[str, dict[str, Any]] = field(default_factory=dict)
    model_routing_file: Path | None = None

    # Quality mode controls how many model-assisted judgment calls are used.
    # "balanced" implements the eight-stage workflow requested by the user:
    # selector, research synthesis, brief, article, model review, conditional
    # revision, conditional final polish, and image generation.
    quality_mode: str = "balanced"
    max_selector_tokens: int = 1400
    max_research_synthesis_tokens: int = 1800
    max_model_review_tokens: int = 1800
    max_final_polish_tokens: int = 10500

    # Local durable memory/cache. These are user-owned files; nothing is sent to
    # a database service unless the user modifies the project to do so.
    editorial_memory_dir: Path | None = None
    cache_dir: Path | None = None
    cache_enabled: bool = True

    # Full-body duplicate and style/review quality controls.
    enable_full_body_duplicate_check: bool = True
    duplicate_body_threshold: float = 0.62
    enable_claim_ledger: bool = True
    max_claims_needing_review: int = 8

    # Article validation controls
    min_article_word_count: int = 1500


@dataclass
class AgentOutputs:
    """Paths written by a completed run."""

    run_dir: Path
    article_md: Path
    featured_image: Path | None
    featured_image_prompt: Path
    topic_brief: Path
    research_json: Path
    candidate_scores_json: Path
    site_articles_json: Path
    events_jsonl: Path
    run_report_json: Path
    claim_ledger_json: Path | None = None
    fact_analysis_boundary_md: Path | None = None
    duplicate_body_report_json: Path | None = None
    publish_request_json: Path | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Return paths as strings for CLI display or downstream automation."""

        return {
            k: (str(v) if v is not None else None) for k, v in asdict(self).items()
        }
