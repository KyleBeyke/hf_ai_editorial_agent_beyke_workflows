"""Small token-budget helpers for prompt construction.

The Hugging Face Inference API charges and limits by tokens, but this educational
package avoids adding a tokenizer dependency.  Instead it uses a conservative
character approximation:

    estimated_tokens ~= characters / 4

That is not exact for every model or language, but it is good enough to keep
research context from ballooning accidentally.  The agent deliberately performs
most research selection, duplicate checking, and source compression in Python so
the LLM receives only the evidence it needs to write the editorial.
"""

from __future__ import annotations

import re
from typing import Iterable

from .schemas import ResearchEvidence


def estimate_tokens(text: str) -> int:
    """Return a rough token estimate without depending on a tokenizer.

    English prose often averages around four characters per token.  We round up
    and add a small cushion so reports err on the side of warning early.
    """

    return max(1, int(len(text) / 4) + 16)


def clean_for_prompt(text: str) -> str:
    """Normalize whitespace and remove common website boilerplate fragments.

    Web pages frequently include repeated menu labels, newsletter text, cookie
    banners, and huge runs of whitespace.  This keeps injected context compact.
    """

    text = re.sub(r"\s+", " ", text or "").strip()
    boilerplate_patterns = [
        r"Subscribe to our newsletter.*?$",
        r"Accept all cookies.*?$",
        r"Sign up.*?newsletter",
        r"Share this article",
    ]
    for pattern in boilerplate_patterns:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def keyword_terms(seed_text: str, extra: Iterable[str] = ()) -> set[str]:
    """Extract useful keywords from a title/summary for compression.

    This is intentionally simple and transparent.  It is not trying to be a
    semantic search engine; it just helps the compressor keep sentences that
    mention the topic's core terms.
    """

    stopwords = {
        "the", "and", "for", "with", "that", "this", "from", "into", "about",
        "what", "when", "where", "why", "how", "are", "was", "were", "has",
        "have", "will", "can", "use", "using", "new", "more", "less",
    }
    words = re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", seed_text.lower())
    return {w for w in words if w not in stopwords} | {x.lower() for x in extra}


def compress_text(text: str, max_chars: int, keywords: set[str] | None = None) -> str:
    """Extractively compress source text to a character budget.

    The function keeps the opening context and then scores sentences by keyword
    hits.  This is cheaper and more predictable than asking the LLM to summarize
    every source before article generation.
    """

    text = clean_for_prompt(text)
    if len(text) <= max_chars:
        return text

    keywords = keywords or set()
    # Split on sentence-ish boundaries while avoiding a heavyweight NLP package.
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if not sentences:
        return text[:max_chars].rstrip()

    # Always keep a small leading excerpt because it often contains the main
    # source framing, then fill the rest with keyword-relevant sentences.
    lead = " ".join(sentences[:2])
    remaining_budget = max(0, max_chars - len(lead) - 20)

    scored: list[tuple[int, int, str]] = []
    for idx, sent in enumerate(sentences[2:], start=2):
        lower = sent.lower()
        score = sum(1 for term in keywords if term in lower)
        # Prefer shorter, dense sentences over huge boilerplate paragraphs.
        if len(sent) < 420:
            score += 1
        scored.append((score, -idx, sent))

    chosen: list[str] = []
    used = 0
    for score, _neg_idx, sent in sorted(scored, reverse=True):
        if score <= 0:
            continue
        if used + len(sent) + 1 > remaining_budget:
            continue
        chosen.append(sent)
        used += len(sent) + 1

    compressed = (lead + " " + " ".join(chosen)).strip()
    return compressed[:max_chars].rstrip()


def render_evidence_for_prompt(
    evidence: list[ResearchEvidence],
    *,
    topic_seed: str,
    max_total_chars: int,
    per_source_chars: int,
) -> str:
    """Render a compact, source-labeled research block for LLM prompts.

    Every item is labeled as source evidence.  The writer model should treat the
    text as facts to verify/synthesize, not as instructions to obey.
    """

    terms = keyword_terms(topic_seed)
    chunks: list[str] = []
    used = 0

    for idx, item in enumerate(evidence, start=1):
        excerpt = compress_text(item.excerpt, max_chars=per_source_chars, keywords=terms)
        block = (
            f"### Evidence {idx}: {item.title}\n"
            f"- URL: {item.url}\n"
            f"- Source: {item.source_name}\n"
            f"- Published/updated: {item.published or 'unknown'}\n"
            f"- Authority score: {item.authority_score:.2f}\n"
            f"- Relevance score: {item.relevance_score:.2f}\n"
            f"- Excerpt: {excerpt}\n"
        )
        if used + len(block) > max_total_chars:
            break
        chunks.append(block)
        used += len(block)

    if not chunks:
        return "No usable research evidence was available."

    return "\n".join(chunks)


def budget_report(*, label: str, text: str) -> dict[str, int | str]:
    """Create a small event payload showing prompt size and estimated tokens."""

    return {
        "label": label,
        "chars": len(text),
        "estimated_tokens": estimate_tokens(text),
    }
