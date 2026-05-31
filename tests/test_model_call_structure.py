import json
from pathlib import Path

from editorial_agent.agent import EditorialAgent
from editorial_agent.events import EventBus
from editorial_agent.schemas import AgentConfig


def test_balanced_offline_run_writes_model_judgment_artifacts(tmp_path):
    """The balanced workflow should expose each model-assisted judgment stage.

    This test does not assert live model quality.  It verifies the architecture:
    topic/angle selection, research synthesis, editorial review, and optional
    final-polish reporting are all visible as artifacts and hook events.
    """

    outputs = EditorialAgent(
        AgentConfig(output_dir=tmp_path, offline=True, generate_image=False),
        prompt_dir=Path("prompts"),
        event_bus=EventBus(),
    ).run()

    run_dir = outputs.run_dir
    assert (run_dir / "topic_angle_selection.json").exists()
    assert (run_dir / "research_synthesis.json").exists()
    assert (run_dir / "model_editorial_review.json").exists()
    assert (run_dir / "final_polish_report.json").exists()

    report = json.loads(outputs.run_report_json.read_text(encoding="utf-8"))
    assert report["call_structure"] == [
        "topic_angle_selection",
        "research_synthesis",
        "topic_brief_generation",
        "article_generation",
        "model_editorial_review",
        "revision_if_needed",
        "final_polish_if_needed",
        "image_generation",
    ]
    routes = report["models"]["stage_routes"]
    assert routes["topic_angle_selection"]["model"] == "openai/gpt-oss-20b:cheapest"
    assert routes["research_synthesis"]["model"] == "deepseek-ai/DeepSeek-V4-Flash:cheapest"
    assert routes["article_generation"]["model"] == "openai/gpt-oss-120b:cheapest"
    assert routes["editorial_review"]["model"] == "deepseek-ai/DeepSeek-V4-Flash:cheapest"

    events = outputs.events_jsonl.read_text(encoding="utf-8")
    for expected in [
        "topic_angle_selection_start",
        "research_synthesis_start",
        "topic_brief_generation_start",
        "article_generation_start",
        "model_editorial_review_start",
    ]:
        assert expected in events
