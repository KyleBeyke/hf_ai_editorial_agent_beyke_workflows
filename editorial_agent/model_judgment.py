"""Model-assisted editorial judgment stages.

This module contains the prompts, parsers, and deterministic fallbacks for the
model calls that are *judgment heavy* rather than purely mechanical.

The rest of the package remains deterministic where authority matters:
publishing, validation, file writes, duplicate scoring, and WordPress gating are
not delegated to the model.  These helpers only ask the model for editorial
judgment that deterministic code is poor at making, such as whether an angle is
interesting, whether the thesis is sharp, or whether the final article deserves
publication.

Every function returns plain JSON-serializable dictionaries so each decision can
be written to disk as an auditable artifact.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .schemas import CandidateTopic, ResearchEvidence, ResearchSufficiencyReport, SiteArticle
from .style_review import StyleReviewReport
from .validation import ValidationResult
from .token_budget import render_evidence_for_prompt


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract the first JSON object from a model response.

    Models sometimes wrap JSON in Markdown fences or add a short preface even
    when instructed not to.  This helper accepts those common variations while
    still failing closed if no valid JSON object is present.
    """

    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove a single fenced block wrapper if present.
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError as e:
        # Log the specific JSON parsing error for debugging
        pass
    except TypeError as e:
        # Handle type errors (e.g., if cleaned is not a string)
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(cleaned[start : end + 1])
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError as e:
            # Log the specific JSON parsing error for debugging
            return {}
        except TypeError as e:
            # Handle type errors
            return {}
    return {}


def topic_angle_selection_prompt(
    candidates: list[CandidateTopic],
    site_articles: list[SiteArticle],
) -> str:
    """Build the prompt for the topic/angle selection call.

    This call asks a cheaper model to make the qualitative decision that a simple
    score cannot fully answer: Which topic is actually interesting right now, and
    what angle makes it meaningfully different from existing posts?
    """

    candidate_lines = []
    for idx, cand in enumerate(candidates[:10], start=1):
        candidate_lines.append(
            f"{idx}. title={cand.title}\n"
            f"   url={cand.url}\n"
            f"   source={cand.source_name}; published={cand.published or 'unknown'}\n"
            f"   deterministic_score={cand.score}; duplicate_risk={cand.duplicate_risk}\n"
            f"   duplicate_reason={cand.duplicate_reason or 'none'}\n"
            f"   summary={cand.summary[:650]}"
        )

    existing_lines = []
    for art in site_articles[:18]:
        existing_lines.append(
            f"- {art.title} | {art.url} | {art.date or 'date unknown'} | {art.excerpt[:350]}"
        )

    return f"""\
TOPIC_ANGLE_SELECTION_TASK

You are the Topic/Angle Selection Agent for beykeworkflows.com.

Goal:
Pick the best article candidate for a business-and-technology editorial about AI.

Answer these model-assisted judgment questions explicitly:
- Is this topic actually interesting?
- Is the angle meaningfully different from prior beykeworkflows.com articles?
- What is the sharpest editorial thesis?
- What are the strongest business consequences?

Constraints:
- Do not select any candidate with duplicate_risk >= 0.70 unless every other candidate is worse.
- Prefer an angle that is timely, business-relevant, technically credible, and not a generic AI trend recap.
- Treat existing KyleBeyke.com articles as live-site duplication evidence.
- Return JSON only. No Markdown.

Candidate topics:
{chr(10).join(candidate_lines)}

Existing KyleBeyke.com AI articles:
{chr(10).join(existing_lines)}

Return exactly this JSON shape:
{{
  "chosen_url": "https://...",
  "chosen_title": "...",
  "interesting_score": 0.0,
  "differentiation_score": 0.0,
  "publication_potential_score": 0.0,
  "angle": "...",
  "sharpest_editorial_thesis": "...",
  "strongest_business_consequences": ["...", "...", "..."],
  "why_this_topic_now": "...",
  "why_not_duplicate": "...",
  "risks_or_caveats": ["...", "..."],
  "decision": "select|reject_all"
}}
"""


def normalize_topic_angle_selection(
    raw: dict[str, Any],
    candidates: list[CandidateTopic],
) -> dict[str, Any]:
    """Normalize/fallback the topic selection result.

    The selected candidate is still checked by deterministic code.  If the model
    response is malformed or points to a duplicate candidate, the highest-scoring
    non-duplicate deterministic candidate is used instead.
    """

    fallback = next((c for c in candidates if c.duplicate_risk < 0.70), candidates[0])
    by_url = {c.url: c for c in candidates}
    chosen = by_url.get(str(raw.get("chosen_url", "")).strip(), fallback)
    if chosen.duplicate_risk >= 0.70:
        chosen = fallback

    def score(name: str, default: float) -> float:
        try:
            return max(0.0, min(1.0, float(raw.get(name, default))))
        except Exception:
            return default

    return {
        "chosen_url": chosen.url,
        "chosen_title": chosen.title,
        "interesting_score": score("interesting_score", max(0.1, chosen.score)),
        "differentiation_score": score("differentiation_score", 1.0 - chosen.duplicate_risk),
        "publication_potential_score": score("publication_potential_score", chosen.score),
        "angle": str(raw.get("angle") or "Frame the topic as a practical business-and-technology decision, not a generic AI trend."),
        "sharpest_editorial_thesis": str(raw.get("sharpest_editorial_thesis") or "The business value of this AI development depends on implementation discipline, not novelty alone."),
        "strongest_business_consequences": list_or_default(
            raw.get("strongest_business_consequences"),
            ["cost control", "workflow reliability", "governance and ownership"],
        ),
        "why_this_topic_now": str(raw.get("why_this_topic_now") or "The topic is recent and connects to current AI implementation decisions."),
        "why_not_duplicate": str(raw.get("why_not_duplicate") or chosen.duplicate_reason or "Deterministic duplicate risk is below the exclusion threshold."),
        "risks_or_caveats": list_or_default(raw.get("risks_or_caveats"), []),
        "decision": "select",
        "fallback_used": chosen.url != str(raw.get("chosen_url", "")).strip(),
        "model_raw": raw,
    }


def research_synthesis_prompt(
    selected: CandidateTopic,
    evidence: list[ResearchEvidence],
    sufficiency: ResearchSufficiencyReport,
    *,
    max_research_chars: int = 6500,
    per_source_chars: int = 1000,
) -> str:
    """Build the research synthesis prompt.

    This call asks a cheaper model to identify what source claims matter most and
    whether the evidence supports a compelling article.  The deterministic
    sufficiency report remains visible so the model cannot pretend thin research
    is strong without contradicting the artifact.
    """

    evidence_block = render_evidence_for_prompt(
        evidence,
        topic_seed=f"{selected.title} {selected.summary}",
        max_total_chars=max_research_chars,
        per_source_chars=per_source_chars,
    )
    return f"""\
RESEARCH_SYNTHESIS_TASK

You are the Research Synthesis Agent for a business-and-technology editorial.

Topic:
- Title: {selected.title}
- URL: {selected.url}
- Summary: {selected.summary}

Deterministic research sufficiency:
- sufficient={sufficiency.sufficient}
- score={sufficiency.score}
- evidence_count={sufficiency.evidence_count}
- authoritative_count={sufficiency.authoritative_count}
- total_excerpt_chars={sufficiency.total_excerpt_chars}
- issues={sufficiency.issues}

Evidence inventory:
{evidence_block}

Answer these model-assisted judgment questions:
- Which source claims matter most?
- Is there enough information to create a compelling article?
- What should the article emphasize?
- What should the article avoid claiming?

Return JSON only:
{{
  "research_enough_for_compelling_article": true,
  "confidence": 0.0,
  "most_important_source_claims": [
    {{"claim": "...", "supporting_urls": ["https://..."], "why_it_matters": "..."}}
  ],
  "business_consequences": ["...", "...", "..."],
  "technical_realities": ["...", "...", "..."],
  "missing_context": ["...", "..."],
  "additional_research_queries": ["...", "..."],
  "article_should_emphasize": ["...", "..."],
  "article_should_avoid_claiming": ["...", "..."]
}}
"""


def normalize_research_synthesis(
    raw: dict[str, Any],
    evidence: list[ResearchEvidence],
    sufficiency: ResearchSufficiencyReport,
) -> dict[str, Any]:
    """Normalize research synthesis with deterministic fallback values."""

    urls = [ev.url for ev in evidence[:5]]
    enough_default = sufficiency.sufficient and sufficiency.score >= 0.7
    return {
        "research_enough_for_compelling_article": bool(raw.get("research_enough_for_compelling_article", enough_default)),
        "confidence": safe_score(raw.get("confidence"), sufficiency.score),
        "most_important_source_claims": raw.get("most_important_source_claims")
        if isinstance(raw.get("most_important_source_claims"), list)
        else [
            {
                "claim": "The collected sources provide implementation context, business consequences, and constraints relevant to the selected AI topic.",
                "supporting_urls": urls,
                "why_it_matters": "The article should be grounded in source-supported realities rather than broad AI hype.",
            }
        ],
        "business_consequences": list_or_default(raw.get("business_consequences"), ["cost", "reliability", "governance"]),
        "technical_realities": list_or_default(raw.get("technical_realities"), ["integration complexity", "validation requirements", "source grounding"]),
        "missing_context": list_or_default(raw.get("missing_context"), sufficiency.issues),
        "additional_research_queries": list_or_default(raw.get("additional_research_queries"), []),
        "article_should_emphasize": list_or_default(raw.get("article_should_emphasize"), ["practical business relevance", "implementation reality"]),
        "article_should_avoid_claiming": list_or_default(raw.get("article_should_avoid_claiming"), ["unsupported statistics", "vendor superiority", "production readiness without evidence"]),
        "model_raw": raw,
    }


def article_generation_addendum(
    angle_selection: dict[str, Any],
    research_synthesis: dict[str, Any],
) -> str:
    """Create a compact addendum injected into brief/article prompts."""

    claims = []
    for item in research_synthesis.get("most_important_source_claims", [])[:6]:
        if isinstance(item, dict):
            urls = ", ".join(item.get("supporting_urls", [])[:3])
            claims.append(f"- {item.get('claim', '')} | URLs: {urls} | Why it matters: {item.get('why_it_matters', '')}")
        else:
            claims.append(f"- {item}")

    return f"""\
## MODEL-ASSISTED EDITORIAL JUDGMENT ADDENDUM

Use this as editorial planning context. Do not treat it as source evidence unless a supporting URL is listed.

Selected angle:
{angle_selection.get('angle')}

Sharpest thesis:
{angle_selection.get('sharpest_editorial_thesis')}

Why this is not a duplicate:
{angle_selection.get('why_not_duplicate')}

Strongest business consequences:
{bullet_lines(angle_selection.get('strongest_business_consequences', []))}

Research synthesis: most important source claims:
{chr(10).join(claims)}

Research synthesis: article should emphasize:
{bullet_lines(research_synthesis.get('article_should_emphasize', []))}

Research synthesis: article should avoid claiming:
{bullet_lines(research_synthesis.get('article_should_avoid_claiming', []))}
"""


def model_editorial_review_prompt(
    article_md: str,
    validation: ValidationResult,
    deterministic_review: Any,
    style_report: StyleReviewReport,
    evidence: list[ResearchEvidence],
) -> str:
    """Build the model editorial review prompt.

    This call explicitly asks the model to judge the qualitative questions that
    deterministic validators cannot reliably answer: insightful versus merely
    correct, generic tone, and whether the package deserves publication.
    """

    evidence_urls = "\n".join(f"- {ev.title}: {ev.url}" for ev in evidence[:10])
    article_excerpt = article_md[:18000]
    return f"""\
EDITORIAL_REVIEW_TASK

You are the Model Editorial Review Agent for a professional business-and-technology blog.

Judge these questions:
- Is the article insightful or just correct?
- Does the article sound generic?
- Does the article deserve publication after normal human review?
- Are the strongest business consequences clear?
- Are source-supported factual claims separated from analysis/opinion?
- Does the article satisfy its purpose for beykeworkflows.com?

Deterministic validation:
- ok={validation.ok}
- issues={validation.issues}
- article_word_count={validation.article_word_count}
- focus_keyword={validation.focus_keyword}

Deterministic editorial review:
- ok={getattr(deterministic_review, 'ok', False)}
- truthfulness_issues={getattr(deterministic_review, 'truthfulness_issues', [])}
- clarity_issues={getattr(deterministic_review, 'clarity_issues', [])}
- purpose_issues={getattr(deterministic_review, 'purpose_issues', [])}

Style review:
- ok={style_report.ok}
- issues={style_report.issues}

Allowed evidence URLs:
{evidence_urls}

Article package:
{article_excerpt}

Return JSON only:
{{
  "deserves_publication_after_human_review": true,
  "insight_score": 0.0,
  "genericness_score": 0.0,
  "truthfulness_score": 0.0,
  "clarity_score": 0.0,
  "purpose_score": 0.0,
  "revision_required": false,
  "must_fix": ["...", "..."],
  "should_improve": ["...", "..."],
  "publication_rationale": "...",
  "final_polish_needed": false,
  "final_polish_instructions": ["...", "..."]
}}
"""


def normalize_model_editorial_review(raw: dict[str, Any], validation: ValidationResult, style_report: StyleReviewReport) -> dict[str, Any]:
    """Normalize the model review into a consistent contract."""

    revision_required = bool(raw.get("revision_required", False)) or not validation.ok
    if style_report.issues:
        revision_required = True
    return {
        "deserves_publication_after_human_review": bool(raw.get("deserves_publication_after_human_review", not revision_required)),
        "insight_score": safe_score(raw.get("insight_score"), 0.65),
        "genericness_score": safe_score(raw.get("genericness_score"), 0.35),
        "truthfulness_score": safe_score(raw.get("truthfulness_score"), 0.7),
        "clarity_score": safe_score(raw.get("clarity_score"), 0.7),
        "purpose_score": safe_score(raw.get("purpose_score"), 0.7),
        "revision_required": revision_required,
        "must_fix": list_or_default(raw.get("must_fix"), validation.issues + style_report.issues),
        "should_improve": list_or_default(raw.get("should_improve"), []),
        "publication_rationale": str(raw.get("publication_rationale") or "Model review normalized from available deterministic checks."),
        "final_polish_needed": bool(raw.get("final_polish_needed", False)),
        "final_polish_instructions": list_or_default(raw.get("final_polish_instructions"), []),
        "model_raw": raw,
    }


def build_model_review_repair_prompt(article_md: str, model_review: dict[str, Any], evidence: list[ResearchEvidence]) -> str:
    """Prompt for a revision pass driven by the model review artifact."""

    allowed_sources = "\n".join(f"- {ev.title}: {ev.url}" for ev in evidence[:10])
    return f"""\
ARTICLE_REVISION_TASK

Revise the full article package below.

Must-fix issues:
{bullet_lines(model_review.get('must_fix', []))}

Should-improve issues:
{bullet_lines(model_review.get('should_improve', []))}

Publication rationale from review:
{model_review.get('publication_rationale')}

Allowed external source URLs:
{allowed_sources}

Rules:
- Return the complete revised article package, not notes.
- Preserve the required WordPress package section order.
- Do not invent URLs, APIs, statistics, or quotes.
- Improve insight and editorial sharpness.
- Remove generic AI-writing phrasing.
- Keep the article practical for business and technical readers.

Article package to revise:
{article_md}
"""


def final_polish_prompt(article_md: str, model_review: dict[str, Any], validation: ValidationResult, style_report: StyleReviewReport) -> str:
    """Build the optional final polish / metadata check prompt."""

    return f"""\
FINAL_POLISH_METADATA_TASK

You are the final polish and metadata check agent.

Task:
Make only necessary improvements to clarity, metadata, section order, SEO fields, Jetpack Social Message, and featured image metadata.
Do not add new factual claims unless they are already supported in the article sources.
Do not change the article's core thesis unless required by the review issues.
Return the complete article package.

Model review polish instructions:
{bullet_lines(model_review.get('final_polish_instructions', []))}

Validation issues:
{validation.issues}

Style issues:
{style_report.issues}

Article package:
{article_md}
"""


def polish_needed(validation: ValidationResult, style_report: StyleReviewReport, model_review: dict[str, Any]) -> bool:
    """Decide whether the final polish call is worth spending tokens on."""

    if not validation.ok:
        return True
    if style_report.issues:
        return True
    if bool(model_review.get("final_polish_needed", False)):
        return True
    if safe_score(model_review.get("clarity_score"), 1.0) < 0.78:
        return True
    if safe_score(model_review.get("purpose_score"), 1.0) < 0.78:
        return True
    return False


def safe_score(value: Any, default: float) -> float:
    """Coerce a model score into [0, 1]."""

    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return default


def list_or_default(value: Any, default: list[str]) -> list[str]:
    """Return a clean list of strings from arbitrary model JSON."""

    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return list(default)


def bullet_lines(items: Any) -> str:
    """Render a list-like value as compact Markdown bullets."""

    values = list_or_default(items, [])
    return "\n".join(f"- {item}" for item in values) if values else "- None"
