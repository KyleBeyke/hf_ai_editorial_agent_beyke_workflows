import json
from pathlib import Path

from editorial_agent.agent import EditorialAgent
from editorial_agent.schemas import AgentConfig
from editorial_agent.events import EventBus


def test_offline_agent_writes_complete_artifacts(tmp_path):
    prompt_dir = Path("prompts")
    cfg = AgentConfig(output_dir=tmp_path, offline=True, generate_image=True)
    outputs = EditorialAgent(cfg, prompt_dir=prompt_dir, event_bus=EventBus()).run()

    assert outputs.article_md.exists()
    assert outputs.featured_image and outputs.featured_image.exists()
    assert outputs.events_jsonl.exists()
    assert outputs.run_report_json.exists()

    report = json.loads(outputs.run_report_json.read_text(encoding="utf-8"))
    assert report["article_validation"]["ok"] is True
    assert report["selected_candidate"]["selected"] is True

    events = outputs.events_jsonl.read_text(encoding="utf-8")
    assert "candidate_selected" in events
    assert "featured_image_generation_end" in events
