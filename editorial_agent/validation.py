"""Output validation for the editorial agent.

Validation does not prove editorial quality, but it catches common automation
failures before the package is delivered:

- missing required sections;
- unresolved placeholders;
- too-short article body;
- missing focus keyword in metadata;
- missing Kyle Beyke authorship metadata;
- missing featured image fields.

The parser intentionally supports the current package format where the
"Consolidated WordPress Content Block" contains level-2 headings intended to be
pasted into WordPress.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


REQUIRED_TOP_LEVEL_SECTIONS = [
    "Title",
    "Author",
    "Focus Keyword",
    "Secondary Keywords",
    "Primary Search Intent",
    "Slug",
    "Meta Description",
    "Excerpt",
    "Tags",
    "Consolidated WordPress Content Block",
    "Jetpack Social Message",
    "Compliance Check",
    "Featured Image Filename Suggestion",
    "Featured Image Alt Text",
    "Featured Image Title",
    "Featured Image Caption",
    "Featured Image Description",
]

REQUIRED_WORDPRESS_BLOCK_SECTIONS = [
    "Article Body",
    "Key Takeaways",
    "Practical Decision Framework",
    "FAQ",
    "Sources",
    "Related articles from Beyke Workflows",
    "Recommended Schema Types",
    "Post-Publication Measurement Plan",
]

PACKAGE_SECTIONS_AFTER_WORDPRESS_BLOCK = [
    "Jetpack Social Message",
    "Compliance Check",
    "Notes on Constrained Sections",
    "Featured Image Filename Suggestion",
    "Featured Image Alt Text",
    "Featured Image Title",
    "Featured Image Caption",
    "Featured Image Description",
]


@dataclass
class ValidationResult:
    ok: bool
    issues: list[str]
    article_word_count: int
    focus_keyword: str | None


def validate_article_package(markdown: str) -> ValidationResult:
    issues: list[str] = []

    for section in REQUIRED_TOP_LEVEL_SECTIONS:
        if not has_heading(markdown, section, level=2):
            issues.append(f"Missing required section: {section}")

    if any(token in markdown for token in ["[PASTE", "[Generate", "[Option", "TODO", "{{"]):
        issues.append("Output appears to contain unresolved placeholders.")

    author = extract_section(markdown, "Author").strip()
    if "Kyle Beyke" not in author:
        issues.append("Author section must identify Kyle Beyke.")

    focus_keyword = first_nonempty_line(extract_section(markdown, "Focus Keyword"))
    meta = extract_section(markdown, "Meta Description").lower()
    if focus_keyword and focus_keyword.lower() not in meta:
        issues.append("Focus keyword not found in meta description.")

    alt_text = extract_section(markdown, "Featured Image Alt Text").lower()
    if focus_keyword and focus_keyword.lower() not in alt_text:
        issues.append("Focus keyword not found in featured image alt text.")

    wordpress_block = extract_consolidated_wordpress_block(markdown)
    if wordpress_block:
        for section in REQUIRED_WORDPRESS_BLOCK_SECTIONS:
            # Accept the legacy Kyle heading for old fixtures, but prefer the
            # current Beyke Workflows heading.
            if section == "Related articles from Beyke Workflows":
                if not (has_heading(wordpress_block, section) or has_heading(wordpress_block, "Related articles from Beyke Workflows")):
                    issues.append(f"Missing WordPress block section: {section}")
            elif not has_heading(wordpress_block, section):
                issues.append(f"Missing WordPress block section: {section}")

    article_body = extract_article_body(markdown)
    word_count = count_words(article_body)
    if word_count < 1500:
        issues.append(f"Article body is too short: {word_count} words.")

    return ValidationResult(ok=not issues, issues=issues, article_word_count=word_count, focus_keyword=focus_keyword)


def has_heading(markdown: str, heading: str, level: int | None = None) -> bool:
    if level is None:
        pattern = rf"^#{{2,4}}\s+{re.escape(heading)}\s*$"
    else:
        pattern = rf"^#{{{level}}}\s+{re.escape(heading)}\s*$"
    return bool(re.search(pattern, markdown, flags=re.MULTILINE))


def first_nonempty_line(text: str) -> str | None:
    for line in text.splitlines():
        cleaned = line.strip().strip("` ")
        if cleaned:
            return cleaned
    return None


def extract_section(markdown: str, heading: str) -> str:
    """Extract content after a level-2 heading until the next package heading.

    This is for top-level package metadata. For the WordPress block, use
    extract_consolidated_wordpress_block or extract_article_body instead because
    the block intentionally contains level-2 headings.
    """

    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    match = re.search(pattern, markdown, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+", markdown[start:], flags=re.MULTILINE)
    end = start + next_match.start() if next_match else len(markdown)
    return markdown[start:end].strip()


def extract_consolidated_wordpress_block(markdown: str) -> str:
    """Extract the paste-ready WordPress block despite nested level-2 headings."""

    match = re.search(r"^##\s+Consolidated WordPress Content Block\s*$", markdown, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    boundary_pattern = r"^##\s+(?:" + "|".join(re.escape(h) for h in PACKAGE_SECTIONS_AFTER_WORDPRESS_BLOCK) + r")\s*$"
    boundary = re.search(boundary_pattern, markdown[start:], flags=re.MULTILINE)
    end = start + boundary.start() if boundary else len(markdown)
    return markdown[start:end].strip()


def extract_markdown_heading_section(markdown: str, heading: str) -> str:
    """Extract a section from a markdown fragment by any level-2 to level-4 heading."""

    pattern = rf"^(##{{1,3}})\s+{re.escape(heading)}\s*$"
    match = re.search(pattern, markdown, flags=re.MULTILINE)
    if not match:
        return ""
    hashes = match.group(1)
    level = len(hashes)
    start = match.end()
    next_match = re.search(rf"^#{{2,{level}}}\s+", markdown[start:], flags=re.MULTILINE)
    end = start + next_match.start() if next_match else len(markdown)
    return markdown[start:end].strip()


def extract_article_body(markdown: str) -> str:
    """Extract the full Article Body from the WordPress content block.

    The article body itself can contain many level-2 section headings. Therefore
    the stop boundary is the required ``## Key Takeaways`` section, not the next
    arbitrary heading.
    """

    wordpress_block = extract_consolidated_wordpress_block(markdown)
    if wordpress_block:
        for level in (2, 3):
            match = re.search(rf"^#{{{level}}}\s+Article Body\s*$", wordpress_block, flags=re.MULTILINE)
            if match:
                start = match.end()
                boundary = re.search(r"^##\s+Key Takeaways\s*$|^###\s+Key Takeaways\s*$", wordpress_block[start:], flags=re.MULTILINE)
                end = start + boundary.start() if boundary else len(wordpress_block)
                return wordpress_block[start:end].strip()
    # Legacy support for older offline fixtures.
    match = re.search(r"^###\s+Article Body\s*$", markdown, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^###\s+Key Takeaways\s*$", markdown[start:], flags=re.MULTILINE)
    end = start + next_match.start() if next_match else len(markdown)
    return markdown[start:end].strip()


def count_words(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))
