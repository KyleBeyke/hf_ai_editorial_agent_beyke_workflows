from editorial_agent.research import ResearchAgent
from editorial_agent.review import EditorialPackageReviewer
from editorial_agent.schemas import AgentConfig, CandidateTopic, ResearchEvidence, SiteArticle, SourceItem, utc_now_iso
from editorial_agent.validation import validate_article_package
from editorial_agent.hf_models import offline_article_package


class NoopHttp:
    def get_text(self, url):
        raise RuntimeError("offline test should not fetch")

    def get_json(self, url):
        raise RuntimeError("offline test should not fetch")


def emit(_event_type, _payload=None):
    return None


def test_research_agent_expands_until_sufficient():
    cfg = AgentConfig(
        offline=True,
        research_min_sources=4,
        research_min_authoritative_sources=2,
        research_min_total_chars=2500,
        research_max_rounds=2,
    )
    selected = CandidateTopic(
        title="AI agent reliability research update",
        url="https://example.com/agent-reliability",
        source_name="Example",
        published=utc_now_iso(),
        summary="AI agents need reliability, workflow validation, memory, MCP, and human review.",
    )
    items = [
        SourceItem(
            "Related agent workflow research",
            "https://example.com/related-agent-workflow",
            "Example",
            utc_now_iso(),
            "agent workflow reliability memory validation human review",
        )
    ]

    evidence, report = ResearchAgent(cfg, NoopHttp(), emit).gather(selected, items)

    assert report.sufficient, report.issues
    assert len(evidence) >= 4
    assert report.authoritative_count >= 2
    assert any("research_expansion" in ev.notes for ev in evidence)


def test_editorial_reviewer_flags_unverified_source():
    selected = CandidateTopic("Topic", "https://example.com/selected", "Example", None, "summary")
    evidence = [
        ResearchEvidence(
            title="Selected",
            url="https://example.com/selected",
            source_name="Example",
            excerpt="source text",
            chars=200,
            relevance_score=1.0,
            authority_score=0.5,
        )
    ]
    site_articles = [SiteArticle("Existing", "https://beykeworkflows.com/existing/", None, "")]
    md = offline_article_package("https://example.com/selected https://beykeworkflows.com/existing/")
    md += "\n\n## Sources\n\n- Bad Source: https://invented.example/not-collected\n"

    validation = validate_article_package(md)
    review = EditorialPackageReviewer().review(
        md,
        selected=selected,
        evidence=evidence,
        site_articles=site_articles,
        validation=validation,
    )

    assert review.revision_required
    assert any("Unverified external source" in issue for issue in review.truthfulness_issues)
