from pathlib import Path

from editorial_agent.model_routing import parse_route_overrides, resolve_model_routes


def test_per_stage_model_routing_file_and_cli_overrides(tmp_path):
    """Routing should allow one model/provider per stage.

    This proves the enhancement requested by the user: synthesis/review can use
    one provider while selection/polish use another, instead of sharing a single
    "small model" lane.
    """

    routing_file = tmp_path / "routes.yaml"
    routing_file.write_text(
        """
topic_angle_selection:
  model: "selector-model"
  provider: "selector-provider"
  temperature: 0.2
research_synthesis:
  model: "synthesis-model"
  provider: "synthesis-provider"
topic_brief:
  model: "brief-model"
  provider: "brief-provider"
article_generation:
  model: "article-model"
  provider: "article-provider"
editorial_review:
  model: "review-model"
  provider: "review-provider"
revision:
  model: "revision-model"
  provider: "revision-provider"
final_polish:
  model: "polish-model"
  provider: "polish-provider"
featured_image:
  model: "image-model"
  provider: "image-provider"
  kind: "image"
""",
        encoding="utf-8",
    )

    routes = resolve_model_routes(
        routing_file=routing_file,
        cli_overrides=parse_route_overrides(
            [
                "editorial_review.model=deepseek-ai/DeepSeek-V4-Pro",
                "editorial_review.provider=together",
                "article_generation.temperature=0.55",
            ]
        ),
    )

    assert routes["topic_angle_selection"].model == "selector-model"
    assert routes["research_synthesis"].model == "synthesis-model"
    assert routes["editorial_review"].model == "deepseek-ai/DeepSeek-V4-Pro"
    assert routes["editorial_review"].provider == "together"
    assert routes["article_generation"].temperature == 0.55
    assert routes["featured_image"].kind == "image"
