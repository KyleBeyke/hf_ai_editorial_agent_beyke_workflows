from editorial_agent.schemas import CandidateTopic, SiteArticle
from editorial_agent.similarity import duplicate_risk


def test_duplicate_risk_flags_partial_duplicate():
    candidate = CandidateTopic(
        title="Structured Outputs for AI Workflows",
        url="https://example.com",
        source_name="test",
        published=None,
        summary="JSON Schema and validation for structured AI outputs in workflows.",
    )
    existing = [
        SiteArticle(
            title="Structured Outputs for AI Workflows: Reliable Guide",
            url="https://beykeworkflows.com/structured-outputs-for-ai-workflows-guide/",
            date="2026-04-29",
            excerpt="Structured outputs for AI workflows help turn free-form model responses into validated data.",
        )
    ]
    risk, reason = duplicate_risk(candidate, existing)
    assert risk >= 0.70
    assert "Structured Outputs" in reason
