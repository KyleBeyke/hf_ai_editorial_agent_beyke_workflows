from editorial_agent.cli import prompt_dir
from editorial_agent.model_routing import default_routing_file


def test_runtime_resources_are_packaged_inside_editorial_agent():
    assert prompt_dir().name == "prompts"
    assert prompt_dir().parent.name == "editorial_agent"
    assert (prompt_dir() / "topic_details_prompt.md").exists()
    assert default_routing_file().parent.name == "config"
    assert default_routing_file().parent.parent.name == "editorial_agent"
    assert default_routing_file().exists()
