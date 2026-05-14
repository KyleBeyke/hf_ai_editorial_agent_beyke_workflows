"""Featured image validation.

The image generator is probabilistic in live mode, and the offline placeholder is
deterministic. This module verifies the file-level and metadata-level properties
that code can check reliably before the package is handed to a human editor.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

from .validation import extract_section


@dataclass
class ImageValidationReport:
    ok: bool
    issues: list[str]
    width: int | None = None
    height: int | None = None
    ratio: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def validate_featured_image(image_path: Path | None, article_md: str, focus_keyword: str | None = None) -> ImageValidationReport:
    """Check image existence, basic dimensions, aspect ratio, and alt text."""

    issues: list[str] = []
    width = height = None
    ratio = None

    if image_path is None:
        issues.append("No featured image was generated.")
    elif not image_path.exists():
        issues.append(f"Featured image file does not exist: {image_path}")
    else:
        try:
            from PIL import Image

            with Image.open(image_path) as img:
                width, height = img.size
                ratio = round(width / height, 3) if height else None
                if width < 1000 or height < 500:
                    issues.append(f"Featured image is smaller than recommended for social sharing: {width}x{height}.")
                if ratio is not None and not (1.6 <= ratio <= 2.0):
                    issues.append(f"Featured image aspect ratio is not close to wide social-card format: {ratio}.")
        except Exception as exc:
            issues.append(f"Could not inspect featured image: {type(exc).__name__}: {exc}")

    alt = extract_section(article_md, "Featured Image Alt Text")
    if not alt.strip():
        issues.append("Featured image alt text is missing.")
    if focus_keyword and focus_keyword.lower() not in alt.lower():
        issues.append("Featured image alt text does not contain the focus keyword.")

    return ImageValidationReport(ok=not issues, issues=issues, width=width, height=height, ratio=ratio)
