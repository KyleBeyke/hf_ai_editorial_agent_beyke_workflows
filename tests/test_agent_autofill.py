from pathlib import Path

from editorial_agent.agent import EditorialAgent
from editorial_agent.schemas import AgentConfig, CandidateTopic
from editorial_agent.validation import extract_section


def test_autofill_adds_missing_featured_image_metadata(tmp_path):
    agent = EditorialAgent(
        AgentConfig(output_dir=tmp_path, offline=True, generate_image=False),
        prompt_dir=Path("prompts"),
    )
    candidate = CandidateTopic(
        title="Trustworthy AI Evaluations for Business",
        url="https://example.com/topic",
        source_name="example",
        published=None,
        summary="summary",
    )
    markdown = """## Title
Trustworthy AI Evaluations for Business

## Author
Kyle Beyke

## Focus Keyword
trustworthy ai evaluation

## Slug
trustworthy-ai-evaluation

## Consolidated WordPress Content Block

## Article Body
This is a sample article body with enough structure for testing.
"""
    hydrated = agent._autofill_required_metadata(markdown, selected=candidate)

    for required in [
        "Featured Image Filename Suggestion",
        "Featured Image Alt Text",
        "Featured Image Title",
        "Featured Image Caption",
        "Featured Image Description",
    ]:
        assert extract_section(hydrated, required).strip()
