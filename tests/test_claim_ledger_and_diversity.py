from editorial_agent.claim_ledger import build_claim_ledger
from editorial_agent.schemas import ResearchEvidence
from editorial_agent.source_diversity import evaluate_source_diversity


def test_claim_ledger_separates_recommendation_and_source_supported_fact():
    md = """## Consolidated WordPress Content Block

### Article Body

OpenAI documentation describes agent workflows for tools. Leaders should fund evaluation before scaling automation.
"""
    evidence = [
        ResearchEvidence(
            title="OpenAI Agents documentation",
            url="https://developers.openai.com/api/docs/guides/agents",
            source_name="OpenAI documentation",
            excerpt="Agents can use tools and workflows.",
            chars=200,
            authority_score=1.0,
        )
    ]
    ledger = build_claim_ledger(md, evidence)
    classes = {record.classification for record in ledger}
    assert "source_supported_fact" in classes
    assert "editorial_recommendation" in classes


def test_source_diversity_flags_single_bucket_and_scores_mixed_sources():
    thin = [
        ResearchEvidence("A", "https://example.com/a", "Example", excerpt="x", chars=200),
        ResearchEvidence("B", "https://example.com/b", "Example", excerpt="x", chars=200),
    ]
    thin_report = evaluate_source_diversity(thin)
    assert thin_report.issues

    mixed = [
        ResearchEvidence("OpenAI", "https://openai.com/news/x", "OpenAI", excerpt="x", chars=200),
        ResearchEvidence("NIST", "https://www.nist.gov/itl/ai-risk-management-framework", "NIST", excerpt="x", chars=200),
        ResearchEvidence("MCP", "https://modelcontextprotocol.io/introduction", "MCP", excerpt="x", chars=200),
    ]
    mixed_report = evaluate_source_diversity(mixed)
    assert mixed_report.score >= 0.9
