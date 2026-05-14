"""Shared helpers for featured-image artifacts.

The agent may receive image filename suggestions from model output, so image
handling must be explicit and centralized.  Keeping extension discovery and
MIME-type mapping in one place prevents drift between review, approval, and
WordPress upload paths.
"""

from __future__ import annotations

from pathlib import Path


# WordPress commonly accepts these web-image formats for featured media.  The
# order is intentional: if a run directory somehow contains multiple images,
# prefer PNG/JPEG first for broad compatibility, then WebP.
SUPPORTED_IMAGE_SUFFIXES: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp")

# MIME types sent to the WordPress REST media endpoint.  Never guess from an
# unknown extension because uploading bytes with the wrong Content-Type can
# create broken media attachments.
IMAGE_CONTENT_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def is_supported_image_path(path: Path) -> bool:
    """Return True when *path* has a supported featured-image extension."""

    return path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES


def featured_image_candidates(run_dir: Path) -> list[Path]:
    """Return existing supported image files in deterministic priority order.

    The workflow writes exactly one featured image, but staged commands and
    manual edits can leave additional files in a run directory.  Sorting by
    filename within each extension keeps behavior reproducible across
    operating systems and filesystems.
    """

    candidates: list[Path] = []
    for suffix in SUPPORTED_IMAGE_SUFFIXES:
        candidates.extend(sorted(run_dir.glob(f"*{suffix}")))
    return [path for path in candidates if path.is_file()]


def first_featured_image(run_dir: Path) -> Path | None:
    """Return the preferred featured image in *run_dir*, if one exists."""

    candidates = featured_image_candidates(run_dir)
    return candidates[0] if candidates else None


def media_content_type(image_path: Path) -> str:
    """Return the WordPress upload content type for a supported image path.

    Raises:
        ValueError: if the file extension is unsupported.
    """

    try:
        return IMAGE_CONTENT_TYPES[image_path.suffix.lower()]
    except KeyError as exc:
        allowed = ", ".join(SUPPORTED_IMAGE_SUFFIXES)
        raise ValueError(f"Unsupported featured image extension '{image_path.suffix}'. Expected one of: {allowed}") from exc
