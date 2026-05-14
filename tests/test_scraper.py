from pathlib import Path
from editorial_agent.scrapers import KyleArchiveScraper


class FakeHttp:
    def __init__(self, html):
        self.html = html
        self.calls = 0

    def get_text(self, url):
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError("stop pagination")
        return self.html


def test_kyle_archive_scraper_parses_titles_dates_and_excerpts():
    html = Path("tests/fixtures/kyle_ai_page.html").read_text(encoding="utf-8")
    articles = KyleArchiveScraper(FakeHttp(html)).scrape("https://beykeworkflows.com/category/writing/tech/ai/")
    assert len(articles) == 2
    assert articles[0].title == "AI Workflow Anatomy: Essential Guide for Business"
    assert articles[0].date == "2026-04-26"
    assert "model calls" in articles[0].excerpt
