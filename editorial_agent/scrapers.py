"""Web collection tools for the editorial agent.

This module contains the "web scraping" portion of the system. It uses public
HTML/RSS/API endpoints and treats all retrieved text as untrusted data. The
agent labels scraped material as source evidence; it never treats web text as
system instructions.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Iterable

import requests
from bs4 import BeautifulSoup

from .schemas import SourceItem, SiteArticle


DEFAULT_FEEDS = [
    # Vendor/research sources with a steady stream of AI-relevant releases.
    "https://openai.com/news/rss.xml",
    "https://www.anthropic.com/news/rss.xml",
    "https://huggingface.co/blog/feed.xml",
    "https://deepmind.google/discover/blog/rss.xml",
    "https://blog.google/technology/ai/rss/",
    "https://www.microsoft.com/en-us/research/feed/",
]


AI_QUERY_TERMS = [
    "AI agents",
    "LLM evaluation",
    "AI workflow",
    "model context protocol",
    "AI safety",
    "structured outputs",
    "retrieval augmented generation",
    "small language models",
    "multimodal AI",
    "AI governance",
]


class HttpClient:
    """Small wrapper around requests so tests can inject fake responses."""

    def __init__(self, timeout: int = 20, user_agent: str | None = None) -> None:
        self.timeout = timeout
        self.headers = {
            "User-Agent": user_agent
            or "Mozilla/5.0 (compatible; HF-AI-Editorial-Agent/0.1)"
        }

    def get_text(self, url: str) -> str:
        """Fetch a URL and return text, raising for HTTP errors."""
        resp = requests.get(url, headers=self.headers, timeout=self.timeout)
        resp.raise_for_status()
        return resp.text

    def get_json(self, url: str) -> dict:
        """Fetch a URL and parse JSON."""
        resp = requests.get(url, headers=self.headers, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()


class SiteArchiveScraper:
    """Scrape configured AI category pages.

    The article generator's pasted prompts require live-site verification and
    verified internal links. This scraper retrieves the archive pages and
    extracts article title, URL, date, and excerpt so the agent can compare
    candidates against actual published posts.
    """

    def __init__(self, http: HttpClient) -> None:
        self.http = http

    def scrape(self, category_url: str, max_pages: int = 6) -> list[SiteArticle]:
        articles: list[SiteArticle] = []
        seen_urls: set[str] = set()

        for page_num in range(1, max_pages + 1):
            url = self._page_url(category_url, page_num)
            try:
                html = self.http.get_text(url)
            except Exception:
                # Stop on the first missing page. Tests can assert partial behavior.
                break

            parsed = self._parse_archive_page(html, base_url=category_url)
            for article in parsed:
                if article.url not in seen_urls:
                    seen_urls.add(article.url)
                    articles.append(article)

            # If a page contains no articles, pagination is probably exhausted.
            if not parsed:
                break

        return articles

    def _page_url(self, category_url: str, page_num: int) -> str:
        if page_num == 1:
            return category_url
        return category_url.rstrip("/") + f"/page/{page_num}/"

    def _parse_archive_page(self, html: str, base_url: str) -> list[SiteArticle]:
        soup = BeautifulSoup(html, "html.parser")
        articles: list[SiteArticle] = []

        for h2 in soup.find_all("h2"):
            link = h2.find("a")
            if not link:
                continue

            title = clean_text(link.get_text(" ", strip=True))
            href = link.get("href") or ""
            if not title or title.lower() in {"posts pagination", "search", "topics"}:
                continue

            url = urllib.parse.urljoin(base_url, href)
            if "/category/" in url or url.rstrip("/") == base_url.rstrip("/"):
                continue

            date = None
            excerpt_parts: list[str] = []

            # Walk siblings after the h2 until the next h2. This is resilient to
            # WordPress archive markup where dates, images, and excerpts are
            # siblings rather than nested in an article tag.
            for sibling in h2.next_siblings:
                if getattr(sibling, "name", None) == "h2":
                    break
                text = clean_text(getattr(sibling, "get_text", lambda *a, **k: str(sibling))(" ", strip=True))
                if not text:
                    continue
                date_match = re.search(r"\[(\d{4}-\d{2}-\d{2})\]", text)
                if date_match and not date:
                    date = date_match.group(1)
                    continue
                if "Read more" in text or text.startswith("Image:"):
                    continue
                excerpt_parts.append(text)

            excerpt = clean_text(" ".join(excerpt_parts))[:1000]
            articles.append(SiteArticle(title=title, url=url, date=date, excerpt=excerpt))

        return articles


class TopicScout:
    """Discover recent AI topics from public feeds and APIs."""

    def __init__(self, http: HttpClient) -> None:
        self.http = http

    def collect(self, lookback_days: int = 21, max_items: int = 50) -> list[SourceItem]:
        items: list[SourceItem] = []

        for feed_url in DEFAULT_FEEDS:
            items.extend(self._collect_feed(feed_url))

        items.extend(self._collect_hn(lookback_days=lookback_days, max_items=25))
        items.extend(self._collect_arxiv(max_items=25))

        # Deduplicate by URL or title.
        deduped: list[SourceItem] = []
        seen: set[str] = set()
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        for item in items:
            key = item.url or item.title.lower()
            if key in seen:
                continue
            seen.add(key)
            if item.published:
                parsed = parse_datetime(item.published)
                if parsed and parsed < cutoff:
                    continue
            deduped.append(item)

        return deduped[:max_items]

    def _collect_feed(self, feed_url: str) -> list[SourceItem]:
        try:
            xml = self.http.get_text(feed_url)
        except Exception:
            return []

        # Use feedparser when available, with an stdlib fallback below.
        try:
            import feedparser  # type: ignore

            parsed = feedparser.parse(xml)
            out = []
            for entry in parsed.entries[:20]:
                out.append(
                    SourceItem(
                        title=clean_text(getattr(entry, "title", "")),
                        url=getattr(entry, "link", ""),
                        source_name=feed_url,
                        published=getattr(entry, "published", None)
                        or getattr(entry, "updated", None),
                        summary=clean_text(getattr(entry, "summary", "")),
                    )
                )
            return [x for x in out if x.title and x.url]
        except Exception:
            return self._collect_feed_xml_fallback(xml, feed_url)

    def _collect_feed_xml_fallback(self, xml: str, feed_url: str) -> list[SourceItem]:
        items: list[SourceItem] = []
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            return items

        # Namespaces are ignored by checking tag suffixes.
        for node in root.iter():
            if not node.tag.lower().endswith("item") and not node.tag.lower().endswith("entry"):
                continue
            title = find_child_text(node, "title")
            link = find_child_text(node, "link")
            if not link:
                link_el = find_child(node, "link")
                link = link_el.attrib.get("href", "") if link_el is not None else ""
            published = (
                find_child_text(node, "pubDate")
                or find_child_text(node, "published")
                or find_child_text(node, "updated")
            )
            summary = find_child_text(node, "description") or find_child_text(node, "summary")
            if title and link:
                items.append(SourceItem(clean_text(title), link, feed_url, published, clean_text(summary)))
        return items[:20]

    def _collect_hn(self, lookback_days: int, max_items: int) -> list[SourceItem]:
        cutoff = int((datetime.now(timezone.utc) - timedelta(days=lookback_days)).timestamp())
        query = urllib.parse.quote("AI OR LLM OR agents OR Anthropic OR OpenAI")
        url = (
            "https://hn.algolia.com/api/v1/search_by_date"
            f"?query={query}&tags=story&numericFilters=created_at_i>{cutoff}&hitsPerPage={max_items}"
        )
        try:
            data = self.http.get_json(url)
        except Exception:
            return []

        out: list[SourceItem] = []
        for hit in data.get("hits", []):
            title = clean_text(hit.get("title") or hit.get("story_title") or "")
            item_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            if title and item_url:
                out.append(
                    SourceItem(
                        title=title,
                        url=item_url,
                        source_name="Hacker News / Algolia",
                        published=hit.get("created_at"),
                        summary=clean_text(hit.get("comment_text") or ""),
                    )
                )
        return out

    def _collect_arxiv(self, max_items: int) -> list[SourceItem]:
        # arXiv has a public Atom API. We search both AI and computation/language.
        query = urllib.parse.quote("cat:cs.AI OR cat:cs.CL OR cat:cs.LG")
        url = (
            "https://export.arxiv.org/api/query?"
            f"search_query={query}&start=0&max_results={max_items}"
            "&sortBy=submittedDate&sortOrder=descending"
        )
        try:
            xml = self.http.get_text(url)
        except Exception:
            return []

        out: list[SourceItem] = []
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            return out

        for entry in [n for n in root if n.tag.endswith("entry")]:
            title = clean_text(find_child_text(entry, "title"))
            summary = clean_text(find_child_text(entry, "summary"))
            published = find_child_text(entry, "published")
            link = ""
            for child in entry:
                if child.tag.endswith("link") and child.attrib.get("href"):
                    link = child.attrib["href"]
                    if child.attrib.get("title") == "pdf":
                        continue
                    break
            if title and link:
                out.append(SourceItem(title, link, "arXiv", published, summary))
        return out


def clean_text(text: str) -> str:
    """Collapse whitespace and strip HTML-ish leftovers."""
    text = re.sub(r"\s+", " ", text or "")
    return text.strip()


def find_child(node: ET.Element, name_suffix: str) -> ET.Element | None:
    for child in node:
        if child.tag.lower().endswith(name_suffix.lower()):
            return child
    return None


def find_child_text(node: ET.Element, name_suffix: str) -> str:
    child = find_child(node, name_suffix)
    if child is not None and child.text:
        return child.text
    return ""


def parse_datetime(value: str | None) -> datetime | None:
    """Parse common RSS/Atom/ISO date formats. Return None when uncertain."""
    if not value:
        return None
    value = value.strip()
    # ISO first.
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        pass
    # RFC 2822/RSS via email.utils.
    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


# Backward-compatible alias for older imports/tests.
KyleArchiveScraper = SiteArchiveScraper
