"""Site and author defaults for the editorial agent.

Keep site identity in one place so code, prompts, tests, and WordPress payloads
do not drift when the publication target changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


DEFAULT_AUTHOR_NAME = "Kyle Beyke"
DEFAULT_SITE_NAME = "Beyke Workflows"
DEFAULT_SITE_BASE_URL = "https://beykeworkflows.com"
DEFAULT_SITE_CATEGORY_URL = "https://beykeworkflows.com/category/writing/tech/ai/"
DEFAULT_RELATED_ARTICLES_HEADING = "Related articles from Beyke Workflows"


@dataclass(frozen=True)
class SiteProfile:
    """Publication identity used in prompts, validation, and WordPress drafts."""

    site_name: str = DEFAULT_SITE_NAME
    author_name: str = DEFAULT_AUTHOR_NAME
    site_base_url: str = DEFAULT_SITE_BASE_URL
    site_category_url: str = DEFAULT_SITE_CATEGORY_URL
    related_articles_heading: str = DEFAULT_RELATED_ARTICLES_HEADING

    @property
    def site_domain(self) -> str:
        return normalize_domain(self.site_base_url or self.site_category_url)

    @property
    def category_domain(self) -> str:
        return normalize_domain(self.site_category_url or self.site_base_url)


def normalize_domain(url_or_domain: str) -> str:
    """Return a normalized domain for URL/domain comparison."""

    value = (url_or_domain or "").strip()
    if not value:
        return ""
    parsed = urlparse(value if "://" in value else f"https://{value}")
    return parsed.netloc.lower().replace("www.", "") or value.lower().replace("www.", "")


def site_profile_from_category_url(
    site_category_url: str | None,
    *,
    site_name: str = DEFAULT_SITE_NAME,
    author_name: str = DEFAULT_AUTHOR_NAME,
    site_base_url: str | None = None,
    related_articles_heading: str = DEFAULT_RELATED_ARTICLES_HEADING,
) -> SiteProfile:
    """Build a profile from a category URL while preserving explicit defaults."""

    category = site_category_url or DEFAULT_SITE_CATEGORY_URL
    base = site_base_url
    if not base:
        parsed = urlparse(category)
        base = f"{parsed.scheme or 'https'}://{parsed.netloc}" if parsed.netloc else DEFAULT_SITE_BASE_URL
    return SiteProfile(
        site_name=site_name,
        author_name=author_name,
        site_base_url=base.rstrip("/"),
        site_category_url=category,
        related_articles_heading=related_articles_heading,
    )


def is_internal_url(url: str, allowed_domains: set[str]) -> bool:
    """Return True when a URL belongs to one of the configured site domains."""

    domain = normalize_domain(url)
    return bool(domain and domain in {normalize_domain(d) for d in allowed_domains if d})
