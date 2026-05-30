"""Human-gated WordPress draft creation.

This module intentionally does not publish live posts. The only supported remote
write is "create a draft" after explicit human acceptance. The acceptance gate is
implemented as a machine-readable approval file plus an explicit CLI flag so a
mistyped command or unattended agent run cannot create a WordPress draft.

Environment variables used by the CLI:

- WP_BASE_URL: e.g. https://beykeworkflows.com
- WP_USERNAME: WordPress username
- WP_APP_PASSWORD: application password
- WP_AUTHOR_ID: optional numeric WordPress author/user ID for Kyle Beyke
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import requests

from .image_files import first_featured_image, media_content_type
from .schemas import utc_now_iso
from .validation import extract_consolidated_wordpress_block, extract_section


@dataclass
class ApprovalRequest:
    """A human-readable approval request generated from a completed run."""

    action: str
    status: str
    run_dir: str
    article_md: str
    featured_image: str | None
    generated_at: str
    approved: bool = False
    approved_by: str | None = None
    approved_at: str | None = None
    notes: str = "Set approved=true, approved_by, and approved_at only after reviewing the article and image."

    def to_dict(self) -> dict:
        return asdict(self)


def create_approval_request(run_dir: Path) -> Path:
    """Create a draft-publishing approval request with approved=false."""

    article = run_dir / "article.md"
    image_candidate = first_featured_image(run_dir)
    req = ApprovalRequest(
        action="create_wordpress_draft",
        status="draft",
        run_dir=str(run_dir.resolve()),
        article_md=str(article.resolve()),
        featured_image=str(image_candidate.resolve()) if image_candidate else None,
        generated_at=utc_now_iso(),
    )
    path = run_dir / "publish_request.json"
    path.write_text(json.dumps(req.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_and_validate_approval(path: Path, run_dir: Path) -> dict[str, Any]:
    """Validate a human approval file before any WordPress request is made."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    expected_run = str(run_dir.resolve())

    errors = []
    if payload.get("action") != "create_wordpress_draft":
        errors.append("Approval action must be create_wordpress_draft.")
    if payload.get("status") != "draft":
        errors.append("Approval status must be draft; this tool never publishes live posts.")
    if payload.get("run_dir") != expected_run:
        errors.append(f"Approval run_dir does not match requested run directory: {expected_run}")
    article_md = payload.get("article_md")
    if not article_md:
        errors.append("Approval file must include article_md.")
    elif not Path(article_md).exists():
        errors.append(f"Approved article file does not exist: {article_md}")
    featured_image = payload.get("featured_image")
    if not featured_image:
        errors.append("Approval file must include featured_image; create or validate the image before draft creation.")
    elif not Path(featured_image).exists():
        errors.append(f"Approved featured image file does not exist: {featured_image}")
    if payload.get("approved") is not True:
        errors.append("Approval file must contain approved=true.")
    if not payload.get("approved_by"):
        errors.append("Approval file must include approved_by.")
    if not payload.get("approved_at"):
        errors.append("Approval file must include approved_at.")
    if errors:
        raise PermissionError("Publishing gate rejected the request: " + " ".join(errors))
    return payload


def wp_auth_header(username: str, app_password: str) -> dict[str, str]:
    """Return WordPress Application Password Basic Auth header."""

    # Validate inputs
    if not username or not app_password:
        raise ValueError("WordPress username and application password are required")

    # Additional validation for credential format
    if len(username) > 100 or len(app_password) > 100:
        raise ValueError("WordPress credentials exceed maximum length")

    token = base64.b64encode(f"{username}:{app_password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def markdown_to_basic_html(markdown: str) -> str:
    """Convert Markdown to simple HTML if markdown package is available.

    WordPress can store Markdown in some setups, but most sites expect HTML. This
    function uses the optional markdown package when installed and otherwise
    sends Markdown inside a <pre> warning-safe fallback for review.
    """

    try:
        import markdown as md

        return md.markdown(markdown, extensions=["tables", "fenced_code"])
    except Exception:
        return "<pre>" + markdown.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + "</pre>"


def wordpress_payload_from_article(article_md: str) -> dict[str, Any]:
    """Build a safe draft post payload from the article package.

    The payload remains draft-only. Authorship is made explicit in two ways:
    the article package must include ``## Author`` with "Kyle Beyke", and the
    optional ``WP_AUTHOR_ID`` environment variable can map the draft to Kyle's
    WordPress user ID when creating the remote draft.
    """

    # Validate input
    if not article_md or not isinstance(article_md, str):
        raise ValueError("Article markdown content is required")

    title_section = extract_section(article_md, "Title").strip()
    title = title_section.splitlines()[0].strip("# ").strip() if title_section else ""
    if not title:
        title = article_md.splitlines()[0].replace("#", "").strip() or "AI Editorial Draft"

    # Validate title
    if len(title) > 255:
        title = title[:252] + "..."

    slug = extract_section(article_md, "Slug").strip().splitlines()[0].strip("` ") if extract_section(article_md, "Slug") else ""
    # Validate slug
    if slug and len(slug) > 200:
        slug = slug[:197] + "..."

    excerpt = extract_section(article_md, "Excerpt").strip()
    # Validate excerpt
    if len(excerpt) > 2000:
        excerpt = excerpt[:1997] + "..."

    content = extract_consolidated_wordpress_block(article_md) or extract_section(article_md, "Consolidated WordPress Content Block") or article_md
    # Validate content
    if len(content) > 100000:  # 100KB limit
        raise ValueError("Article content exceeds maximum size limit")

    payload: dict[str, Any] = {
        "title": title,
        "slug": slug,
        "excerpt": excerpt,
        "content": markdown_to_basic_html(content),
        "status": "draft",
    }

    # Validate author ID if provided
    author_id = os.getenv("WP_AUTHOR_ID")
    if author_id:
        try:
            payload["author"] = int(author_id)
        except ValueError:
            raise RuntimeError("WP_AUTHOR_ID must be numeric if set.")

    return payload


class WordPressDraftClient:
    """Minimal WordPress REST API client that can create drafts only."""

    def __init__(self, base_url: str, username: str, app_password: str, timeout: int = 30) -> None:
        # Validate inputs
        if not base_url:
            raise ValueError("WordPress base URL is required")
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("WordPress base URL must start with http:// or https://")
        if not username or not app_password:
            raise ValueError("WordPress username and application password are required")

        self.base_url = base_url.rstrip("/")
        self.auth = wp_auth_header(username, app_password)
        self.timeout = timeout
        # Store sanitized credentials info for logging
        self._username = username
        self._app_password_masked = "*" * min(8, len(app_password)) if app_password else ""

    @classmethod
    def from_env(cls) -> "WordPressDraftClient":
        missing = [name for name in ["WP_BASE_URL", "WP_USERNAME", "WP_APP_PASSWORD"] if not os.getenv(name)]
        if missing:
            raise RuntimeError("Missing WordPress environment variables: " + ", ".join(missing))

        base_url = os.environ["WP_BASE_URL"]
        # Validate URL format
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("WP_BASE_URL must start with http:// or https://")

        return cls(base_url, os.environ["WP_USERNAME"], os.environ["WP_APP_PASSWORD"])

    def upload_media(self, image_path: Path) -> int:
        """Upload media and return WordPress media ID."""

        url = f"{self.base_url}/wp-json/wp/v2/media"
        headers = dict(self.auth)
        headers["Content-Disposition"] = f'attachment; filename="{image_path.name}"'
        headers["Content-Type"] = media_content_type(image_path)

        # Sanitize headers for logging
        sanitized_headers = {k: v if k != "Authorization" else "[REDACTED]" for k, v in headers.items()}

        # Retry logic with exponential backoff
        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = requests.post(url, headers=headers, data=image_path.read_bytes(), timeout=self.timeout)
                resp.raise_for_status()
                return int(resp.json()["id"])
            except requests.RequestException as e:
                if attempt == max_retries - 1:  # Last attempt
                    # Sanitize error message to avoid credential exposure
                    error_msg = str(e)
                    if self._app_password_masked in error_msg:
                        error_msg = re.sub(re.escape(self._app_password_masked), "[REDACTED]", error_msg)
                    raise requests.RequestException(f"Failed to upload media after {max_retries} attempts: {error_msg}") from e
                else:
                    # Exponential backoff
                    time.sleep(2 ** attempt)

    def create_draft(self, article_md: str, featured_image_id: int | None = None) -> dict[str, Any]:
        """Create a WordPress draft post. The status is forcibly set to draft."""

        payload = wordpress_payload_from_article(article_md)
        payload["status"] = "draft"  # Hard safety control: never trust caller-provided status.
        if featured_image_id:
            payload["featured_media"] = featured_image_id

        # Retry logic with exponential backoff
        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = requests.post(
                    f"{self.base_url}/wp-json/wp/v2/posts",
                    headers={**self.auth, "Content-Type": "application/json"},
                    data=json.dumps(payload),
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") != "draft":
                    raise RuntimeError(f"WordPress returned non-draft status; refusing to continue: {data.get('status')}")
                return data
            except requests.RequestException as e:
                if attempt == max_retries - 1:  # Last attempt
                    # Sanitize error message to avoid credential exposure
                    error_msg = str(e)
                    if self._app_password_masked in error_msg:
                        error_msg = re.sub(re.escape(self._app_password_masked), "[REDACTED]", error_msg)
                    raise requests.RequestException(f"Failed to create draft after {max_retries} attempts: {error_msg}") from e
                else:
                    # Exponential backoff
                    time.sleep(2 ** attempt)


def create_wordpress_draft_with_gate(run_dir: Path, approval_file: Path, *, dry_run: bool = False) -> dict[str, Any]:
    """Validate approval, then optionally create a draft in WordPress."""

    approval = load_and_validate_approval(approval_file, run_dir)
    article_path = Path(approval["article_md"])
    image_path = Path(approval["featured_image"]) if approval.get("featured_image") else None
    article_md = article_path.read_text(encoding="utf-8")

    if image_path is None or not image_path.exists():
        raise FileNotFoundError("Approval references no existing featured image; refusing to create an incomplete WordPress draft.")

    if dry_run:
        return {"dry_run": True, "status": "draft", "approval": approval, "payload": wordpress_payload_from_article(article_md)}

    client = WordPressDraftClient.from_env()
    media_id = client.upload_media(image_path)
    post = client.create_draft(article_md, featured_image_id=media_id)
    return {"status": "draft", "media_id": media_id, "post": post, "approval": approval}
