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

PACKAGE_HEADING_ALIASES = REQUIRED_TOP_LEVEL_SECTIONS + [
    "Notes on Constrained Sections",
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


def validate_article_package(markdown: str, min_word_count: int = 1500) -> ValidationResult:
    markdown = normalize_package_markdown(markdown)
    issues: list[str] = []

    for section in REQUIRED_TOP_LEVEL_SECTIONS:
        if not has_heading(markdown, section, level=2):
            issues.append(f"Missing required section: {section}")

    # Check for unresolved placeholders using more precise pattern matching
    placeholder_patterns = [
        r'\[PASTE\s+[^]]*?\]',      # [PASTE ...] patterns
        r'\[Generate\s+[^]]*?\]',   # [Generate ...] patterns
        r'\[Option\s+[^]]*?\]',     # [Option ...] patterns
        r'\bTODO\b',                # TODO not in code/comments
        r'\{\{[^}]*?\}\}',          # {{...}} patterns
    ]

    for pattern in placeholder_patterns:
        # Only match placeholders outside of code blocks
        code_block_pattern = r'```.*?```|`[^`]*`'
        # Remove code blocks for placeholder detection
        content_without_code = re.sub(code_block_pattern, '', markdown, flags=re.DOTALL)
        if re.search(pattern, content_without_code, re.IGNORECASE):
            issues.append("Output appears to contain unresolved placeholders.")
            break  # Only report once

    author = extract_section(markdown, "Author").strip()
    # Case-insensitive check with whitespace normalization
    normalized_author = re.sub(r'\s+', ' ', author).strip()
    if not re.search(r'kyle\s+beyke', normalized_author, re.IGNORECASE):
        issues.append("Author section must identify Kyle Beyke.")

    focus_keyword = first_nonempty_line(extract_section(markdown, "Focus Keyword"))
    if focus_keyword:
        # Use word boundary matching to prevent partial matches
        escaped_keyword = re.escape(focus_keyword.strip())
        meta = extract_section(markdown, "Meta Description")
        if not re.search(rf'\b{escaped_keyword}\b', meta, re.IGNORECASE):
            issues.append("Focus keyword not found in meta description.")

    if focus_keyword:
        # Use word boundary matching for alt text as well
        escaped_keyword = re.escape(focus_keyword.strip())
        alt_text = extract_section(markdown, "Featured Image Alt Text")
        if not re.search(rf'\b{escaped_keyword}\b', alt_text, re.IGNORECASE):
            issues.append("Focus keyword not found in featured image alt text.")

    wordpress_block = extract_consolidated_wordpress_block(markdown)
    if wordpress_block:
        for section in REQUIRED_WORDPRESS_BLOCK_SECTIONS:
            # Standardize on current Beyke Workflows heading
            if section == "Related articles from Beyke Workflows":
                if not has_heading(wordpress_block, section):
                    issues.append(f"Missing WordPress block section: {section}")
            elif not has_heading(wordpress_block, section):
                issues.append(f"Missing WordPress block section: {section}")

    article_body = extract_article_body(markdown)
    word_count = count_words(article_body)
    if word_count < min_word_count:
        issues.append(f"Article body is too short: {word_count} words (minimum: {min_word_count}).")

    return ValidationResult(ok=not issues, issues=issues, article_word_count=word_count, focus_keyword=focus_keyword)


def has_heading(markdown: str, heading: str, level: int | None = None) -> bool:
    markdown = normalize_package_markdown(markdown)
    heading_pattern = heading_regex_fragment(heading)
    if level is None:
        pattern = rf"^#{{2,4}}\s+{heading_pattern}\s*$"
    else:
        pattern = rf"^#{{{level}}}\s+{heading_pattern}\s*$"
    return bool(re.search(pattern, markdown, flags=re.MULTILINE))


def first_nonempty_line(text: str) -> str | None:
    for line in text.splitlines():
        cleaned = strip_inline_markdown(line.strip())
        if cleaned:
            return cleaned
    return None


def extract_section(markdown: str, heading: str) -> str:
    """Extract content after a level-2 heading until the next package heading.

    This is for top-level package metadata. For the WordPress block, use
    extract_consolidated_wordpress_block or extract_article_body instead because
    the block intentionally contains level-2 headings.
    """

    markdown = normalize_package_markdown(markdown)
    pattern = rf"^##\s+{heading_regex_fragment(heading)}\s*$"
    match = re.search(pattern, markdown, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+", markdown[start:], flags=re.MULTILINE)
    end = start + next_match.start() if next_match else len(markdown)
    return markdown[start:end].strip()


def extract_consolidated_wordpress_block(markdown: str) -> str:
    """Extract the paste-ready WordPress block despite nested level-2 headings."""

    markdown = normalize_package_markdown(markdown)
    match = re.search(r"^##\s+Consolidated WordPress Content Block\s*$", markdown, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    boundary_pattern = (
        r"^##\s+(?:"
        + "|".join(heading_regex_fragment(h) for h in PACKAGE_SECTIONS_AFTER_WORDPRESS_BLOCK)
        + r")\s*$"
    )
    boundary = re.search(boundary_pattern, markdown[start:], flags=re.MULTILINE)
    end = start + boundary.start() if boundary else len(markdown)
    return markdown[start:end].strip()


def extract_markdown_heading_section(markdown: str, heading: str) -> str:
    """Extract a section from a markdown fragment by any level-2 to level-4 heading."""

    markdown = normalize_package_markdown(markdown)
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

    markdown = normalize_package_markdown(markdown)
    wordpress_block = extract_consolidated_wordpress_block(markdown)
    if wordpress_block:
        for level in (2, 3):
            match = re.search(rf"^#{{{level}}}\s+Article Body\s*$", wordpress_block, flags=re.MULTILINE)
            if match:
                start = match.end()
                boundary = re.search(r"^##\s+Key Takeaways\s*$|^###\s+Key Takeaways\s*$", wordpress_block[start:], flags=re.MULTILINE)
                end = start + boundary.start() if boundary else len(wordpress_block)
                return wordpress_block[start:end].strip()
    # Support simplified package fixtures that place Article Body as a top-level section.
    top_level_article_body = extract_section(markdown, "Article Body")
    if top_level_article_body:
        return top_level_article_body
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


def normalize_package_markdown(markdown: str) -> str:
    """Normalize common heading formatting drifts into canonical package headings.

    Live models sometimes emit top-level metadata as bold labels like:
        **Title**
    instead of:
        ## Title
    This keeps downstream validation/parsing resilient while preserving content.
    """

    normalized = markdown.replace("\r\n", "\n")
    for heading in PACKAGE_HEADING_ALIASES:
        bold_heading = rf"^\s*\*\*\s*{re.escape(heading)}\s*\*\*\s*$"
        normalized = re.sub(bold_heading, f"## {heading}", normalized, flags=re.MULTILINE)
    # Normalize common heading variants emitted by models so deterministic
    # section checks and WordPress extraction remain stable.
    practical_framework_variants = [
        (r"^##\s+Decision[-\u2010-\u2015\u2212 ]Making Framework\s*$", "## Practical Decision Framework"),
        (r"^###\s+Decision[-\u2010-\u2015\u2212 ]Making Framework\s*$", "### Practical Decision Framework"),
        (r"^##\s+Decision Framework\s*$", "## Practical Decision Framework"),
        (r"^###\s+Decision Framework\s*$", "### Practical Decision Framework"),
    ]
    for pattern, replacement in practical_framework_variants:
        normalized = re.sub(pattern, replacement, normalized, flags=re.MULTILINE)
    return normalized


def strip_inline_markdown(text: str) -> str:
    """Strip lightweight inline Markdown formatting around a metadata value."""

    cleaned = text.strip().strip("` ").strip()
    cleaned = re.sub(r"^\*{1,2}(.*?)\*{1,2}$", r"\1", cleaned)
    cleaned = re.sub(r"^_{1,2}(.*?)_{1,2}$", r"\1", cleaned)
    cleaned = re.sub(r"\[(.*?)\]\([^)]*\)", r"\1", cleaned)
    return cleaned.strip()


def heading_regex_fragment(heading: str) -> str:
    """Return a heading regex that tolerates common unicode dash variants."""

    escaped = re.escape(heading)
    return escaped.replace(r"\-", r"[-\u2010-\u2015\u2212]")
