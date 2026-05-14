"""Per-stage Hugging Face model routing.

The agent has several qualitatively different model jobs. A topic selector,
research synthesizer, article writer, reviewer, reviser, and image generator do
not need the same model. This module keeps those choices outside the workflow so
operators can tune quality/cost without editing orchestration code.

Supported configuration sources, in precedence order:

1. built-in defaults;
2. optional YAML/JSON routing file;
3. legacy lane defaults from the CLI/env (`--text-model`, `--small-text-model`);
4. stage-specific environment variables;
5. `--route stage.key=value` CLI overrides.

The YAML reader is intentionally tiny and supports the simple mapping structure
used by editorial_agent/config/model_routing.yaml. If PyYAML is installed, richer YAML syntax
also works.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
import json
import os
import re


TEXT_STAGES = {
    "topic_angle_selection",
    "research_synthesis",
    "topic_brief",
    "article_generation",
    "editorial_review",
    "revision",
    "final_polish",
}

IMAGE_STAGES = {"featured_image"}

ALL_STAGES = TEXT_STAGES | IMAGE_STAGES


@dataclass
class ModelRoute:
    """One model/provider selection for one agent stage."""

    model: str
    provider: str
    temperature: float | None = None
    max_tokens: int | None = None
    kind: str = "text"

    def to_dict(self) -> dict[str, Any]:
        """Serialize the route into JSON-friendly data."""

        return asdict(self)


# Opinionated defaults based on the desired quality/cost split. These can be
# changed without modifying the agent loop by editing editorial_agent/config/model_routing.yaml.
DEFAULT_STAGE_ROUTES: dict[str, dict[str, Any]] = {
    "topic_angle_selection": {
        "model": "Qwen/Qwen3.6-35B-A3B",
        "provider": "deepinfra",
        "temperature": 0.2,
        "kind": "text",
    },
    "research_synthesis": {
        "model": "deepseek-ai/DeepSeek-V4-Pro",
        "provider": "together",
        "temperature": 0.15,
        "kind": "text",
    },
    "topic_brief": {
        "model": "openai/gpt-oss-120b",
        "provider": "together",
        "temperature": 0.35,
        "kind": "text",
    },
    "article_generation": {
        "model": "openai/gpt-oss-120b",
        "provider": "together",
        "temperature": 0.55,
        "kind": "text",
    },
    "editorial_review": {
        "model": "deepseek-ai/DeepSeek-V4-Pro",
        "provider": "together",
        "temperature": 0.1,
        "kind": "text",
    },
    "revision": {
        "model": "openai/gpt-oss-120b",
        "provider": "together",
        "temperature": 0.45,
        "kind": "text",
    },
    "final_polish": {
        "model": "Qwen/Qwen3.6-35B-A3B",
        "provider": "deepinfra",
        "temperature": 0.2,
        "kind": "text",
    },
    "featured_image": {
        "model": "black-forest-labs/FLUX.1-Krea-dev",
        "provider": "fal-ai",
        "kind": "image",
    },
}


# Legacy lane mapping preserves backward compatibility with older CLI/env
# settings. If a user passes only --text-model and --small-text-model, the agent
# can still route stages sensibly.
LEGACY_LANE_FOR_STAGE = {
    "topic_angle_selection": "small",
    "research_synthesis": "small",
    "topic_brief": "heavy",
    "article_generation": "heavy",
    "editorial_review": "small",
    "revision": "heavy",
    "final_polish": "small",
    "featured_image": "image",
}


def default_routing_file(project_root: Path | None = None) -> Path:
    """Return the package's conventional routing file location."""

    base = project_root or Path(__file__).resolve().parent
    return base / "config" / "model_routing.yaml"


def parse_route_overrides(overrides: list[str] | None) -> dict[str, dict[str, Any]]:
    """Parse `--route stage.key=value` CLI overrides.

    Examples:
        --route editorial_review.model=deepseek-ai/DeepSeek-V4-Pro
        --route editorial_review.provider=together
        --route article_generation.temperature=0.55
    """

    parsed: dict[str, dict[str, Any]] = {}
    for item in overrides or []:
        if "=" not in item or "." not in item.split("=", 1)[0]:
            raise ValueError(f"Invalid --route override {item!r}; expected stage.key=value.")
        left, value = item.split("=", 1)
        stage, key = left.split(".", 1)
        stage = normalize_stage_name(stage)
        if stage not in ALL_STAGES:
            raise ValueError(f"Unknown model route stage {stage!r}. Valid stages: {sorted(ALL_STAGES)}")
        parsed.setdefault(stage, {})[key] = coerce_scalar(value)
    return parsed


def resolve_model_routes(
    *,
    routing_file: Path | None = None,
    use_file_defaults: bool = True,
    heavy_model: str = "openai/gpt-oss-120b",
    heavy_provider: str = "together",
    small_model: str = "Qwen/Qwen3.6-35B-A3B",
    small_provider: str = "deepinfra",
    image_model: str = "black-forest-labs/FLUX.1-Krea-dev",
    image_provider: str = "fal-ai",
    cli_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, ModelRoute]:
    """Resolve final routes for all stages.

    The function returns complete `ModelRoute` objects for every known stage.
    Missing values are filled from built-in defaults or legacy lane values.
    """

    routes: dict[str, dict[str, Any]] = deepcopy(DEFAULT_STAGE_ROUTES)

    if use_file_defaults and routing_file and routing_file.exists():
        merge_routes(routes, load_routes_from_file(routing_file))

    # Apply legacy lane values only when there is no explicit routing file.
    # This keeps old CLI flags useful without accidentally overwriting the new
    # per-stage config file. Stage-specific env/CLI overrides below still win.
    if not (use_file_defaults and routing_file and routing_file.exists()):
        apply_legacy_lanes(
            routes,
            heavy_model=heavy_model,
            heavy_provider=heavy_provider,
            small_model=small_model,
            small_provider=small_provider,
            image_model=image_model,
            image_provider=image_provider,
        )

    merge_routes(routes, env_route_overrides())
    merge_routes(routes, cli_overrides or {})

    complete: dict[str, ModelRoute] = {}
    for stage in sorted(ALL_STAGES):
        raw = routes.get(stage, {})
        if not raw.get("model") or not raw.get("provider"):
            raise ValueError(f"Route for {stage!r} must include model and provider.")
        complete[stage] = ModelRoute(
            model=str(raw["model"]),
            provider=str(raw["provider"]),
            temperature=float(raw["temperature"]) if raw.get("temperature") is not None else None,
            max_tokens=int(raw["max_tokens"]) if raw.get("max_tokens") is not None else None,
            kind=str(raw.get("kind") or ("image" if stage in IMAGE_STAGES else "text")),
        )
    return complete


def apply_legacy_lanes(
    routes: dict[str, dict[str, Any]],
    *,
    heavy_model: str,
    heavy_provider: str,
    small_model: str,
    small_provider: str,
    image_model: str,
    image_provider: str,
) -> None:
    """Apply old heavy/small/image lane settings to stage routes."""

    for stage, lane in LEGACY_LANE_FOR_STAGE.items():
        routes.setdefault(stage, {})
        if lane == "heavy":
            routes[stage]["model"] = heavy_model
            routes[stage]["provider"] = heavy_provider
        elif lane == "small":
            routes[stage]["model"] = small_model
            routes[stage]["provider"] = small_provider
        else:
            routes[stage]["model"] = image_model
            routes[stage]["provider"] = image_provider


def env_route_overrides() -> dict[str, dict[str, Any]]:
    """Read stage-specific environment overrides.

    Supported names for a stage like `research_synthesis`:
    - HF_RESEARCH_SYNTHESIS_MODEL
    - HF_RESEARCH_SYNTHESIS_PROVIDER
    - HF_RESEARCH_SYNTHESIS_TEMPERATURE
    - HF_MODEL_RESEARCH_SYNTHESIS
    - HF_PROVIDER_RESEARCH_SYNTHESIS
    """

    result: dict[str, dict[str, Any]] = {}
    for stage in ALL_STAGES:
        prefix = stage.upper()
        model = os.getenv(f"HF_{prefix}_MODEL") or os.getenv(f"HF_MODEL_{prefix}")
        provider = os.getenv(f"HF_{prefix}_PROVIDER") or os.getenv(f"HF_PROVIDER_{prefix}")
        temperature = os.getenv(f"HF_{prefix}_TEMPERATURE")
        max_tokens = os.getenv(f"HF_{prefix}_MAX_TOKENS")
        if model or provider or temperature or max_tokens:
            result[stage] = {}
            if model:
                result[stage]["model"] = model
            if provider:
                result[stage]["provider"] = provider
            if temperature:
                result[stage]["temperature"] = coerce_scalar(temperature)
            if max_tokens:
                result[stage]["max_tokens"] = coerce_scalar(max_tokens)
    return result


def merge_routes(target: dict[str, dict[str, Any]], source: dict[str, dict[str, Any]]) -> None:
    """Merge route dictionaries while normalizing stage names."""

    for stage, data in source.items():
        normalized = normalize_stage_name(stage)
        if normalized not in ALL_STAGES:
            raise ValueError(f"Unknown model route stage {stage!r}. Valid stages: {sorted(ALL_STAGES)}")
        target.setdefault(normalized, {})
        for key, value in (data or {}).items():
            target[normalized][key] = value


def load_routes_from_file(path: Path) -> dict[str, dict[str, Any]]:
    """Load routes from JSON or simple YAML."""

    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = load_yaml_like(text)
    if not isinstance(data, dict):
        raise ValueError(f"Model routing file {path} must contain a mapping.")
    return {normalize_stage_name(k): dict(v or {}) for k, v in data.items()}


def load_yaml_like(text: str) -> dict[str, dict[str, Any]]:
    """Load the simple YAML structure used by this project.

    PyYAML is used when available. If it is not installed, this fallback parser
    accepts a mapping of stages to indented key/value pairs. It deliberately
    avoids advanced YAML features so the config remains readable and auditable.
    """

    try:  # pragma: no cover - depends on optional environment package
        import yaml

        data = yaml.safe_load(text) or {}
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    result: dict[str, dict[str, Any]] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        # Remove comments while preserving values before the comment marker.
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith((" ", "\t")) and line.endswith(":"):
            current = normalize_stage_name(line[:-1].strip())
            result.setdefault(current, {})
            continue
        if current is None:
            continue
        match = re.match(r"^\s+([A-Za-z0-9_\-]+)\s*:\s*(.*?)\s*$", line)
        if match:
            key, value = match.groups()
            result[current][key] = coerce_scalar(value)
    return result


def coerce_scalar(value: Any) -> Any:
    """Convert simple YAML/CLI scalars into Python types."""

    if not isinstance(value, str):
        return value
    value = value.strip().strip('"').strip("'")
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.lower() in {"null", "none", ""}:
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def normalize_stage_name(stage: str) -> str:
    """Normalize aliases used in docs, CLI, and code."""

    normalized = stage.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "selector": "topic_angle_selection",
        "topic_selector": "topic_angle_selection",
        "angle_selection": "topic_angle_selection",
        "synthesis": "research_synthesis",
        "writer": "article_generation",
        "review": "editorial_review",
        "reviser": "revision",
        "polish": "final_polish",
        "image": "featured_image",
    }
    return aliases.get(normalized, normalized)


def routes_to_dict(routes: dict[str, ModelRoute]) -> dict[str, dict[str, Any]]:
    """Serialize all routes for run reports and debugging."""

    return {stage: route.to_dict() for stage, route in sorted(routes.items())}
