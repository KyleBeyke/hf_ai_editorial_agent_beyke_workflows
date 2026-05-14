"""Style checks that reduce generic AI-generated prose.

The article prompts already warn against certain phrases. This deterministic
review catches the most common violations so the revision agent can remove them
before delivery.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict


GENERIC_AI_PHRASES = [
    "in today’s rapidly evolving landscape",
    "in today's rapidly evolving landscape",
    "artificial intelligence is transforming",
    "unlock the power",
    "harness the potential",
    "game-changing",
    "seamlessly",
    "revolutionize",
    "delve into",
    "robust solution",
    "cutting-edge",
    "ever-evolving",
]


@dataclass
class StyleReviewReport:
    ok: bool
    issues: list[str]
    phrase_hits: dict[str, int]

    def to_dict(self) -> dict:
        return asdict(self)


def review_style(markdown: str) -> StyleReviewReport:
    """Find obvious generic-AI-writing phrases and weak editorial signals."""

    lower = markdown.lower()
    hits = {phrase: lower.count(phrase) for phrase in GENERIC_AI_PHRASES if phrase in lower}
    issues = [f"Generic AI/corporate phrase appears {count}x: {phrase}" for phrase, count in hits.items()]

    if len(re.findall(r"\bAI\b", markdown)) > 70:
        issues.append("The article may overuse 'AI' mechanically; check for keyword stuffing.")

    return StyleReviewReport(ok=not issues, issues=issues, phrase_hits=hits)
