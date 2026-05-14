from editorial_agent.schemas import SourceItem, SiteArticle, utc_now_iso
from editorial_agent.scoring import CandidateSelector


def test_candidate_selection_excludes_duplicate_like_topic():
    site_articles = [
        SiteArticle(
            "AI Model Selection: Powerful Guide for Smart Business AI",
            "https://beykeworkflows.com/ai-model-selection-business-ai-guide/",
            "2026-05-07",
            "AI model selection balances quality, cost, latency, risk, and evaluation.",
        )
    ]
    sources = [
        SourceItem(
            "AI Model Selection Rules for Business",
            "https://example.com/dup",
            "test",
            utc_now_iso(),
            "A story about choosing models by quality, cost, latency, risk and evaluation.",
        ),
        SourceItem(
            "New AI Agent Reliability Patterns for Enterprise Workflows",
            "https://example.com/new",
            "test",
            utc_now_iso(),
            "A story about AI agents, workflow reliability, evaluation, memory, and governance.",
        ),
    ]
    candidates = CandidateSelector().build_candidates(sources, site_articles)
    selected = next(c for c in candidates if c.selected)
    assert selected.url == "https://example.com/new"
    assert selected.duplicate_risk < 0.70
