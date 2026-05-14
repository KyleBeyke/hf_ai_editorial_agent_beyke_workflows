# Model Selection Notes

The agent uses Hugging Face Inference Providers through a per-stage routing layer. The goal is not to run the largest model for every job. The goal is to match each stage to the cheapest model likely to do that stage well, while reserving stronger models for heavy editorial writing and revision.

## Where routes are configured

The default routes live in:

```text
config/model_routing.yaml
```

Each stage has its own model, provider, and optional temperature:

```yaml
research_synthesis:
  model: "deepseek-ai/DeepSeek-V4-Pro"
  provider: "together"
  temperature: 0.15
```

The final resolved routes are written into every run report:

```text
run_report.json → models → stage_routes
```

That makes model experiments auditable.

## Default per-stage routing

| Stage | Default model | Default provider | Why |
|---|---|---|---|
| Topic/angle selection | `Qwen/Qwen3.6-35B-A3B` | `deepinfra` | Compact structured judgment about interestingness, differentiation, thesis, and business consequences. |
| Research synthesis | `deepseek-ai/DeepSeek-V4-Pro` | `together` | Stronger synthesis/critique of source claims and missing context. |
| Topic brief | `openai/gpt-oss-120b` | `together` | Heavier prompt-following and editorial planning. |
| Article generation | `openai/gpt-oss-120b` | `together` | Highest-value prose-generation stage. |
| Editorial review | `deepseek-ai/DeepSeek-V4-Pro` | `together` | Independent critique for insight, genericness, truthfulness, clarity, and purpose. |
| Revision, if needed | `openai/gpt-oss-120b` | `together` | Full article-package rewrite when review gates fail. |
| Final polish, if needed | `Qwen/Qwen3.6-35B-A3B` | `deepinfra` | Metadata/style/clarity repair when the extra call is justified. |
| Featured image | `black-forest-labs/FLUX.1-Krea-dev` | `fal-ai` | Professional text-to-image generation. |

## Override routes without editing files

Use `--route stage.key=value`:

```powershell
python -m editorial_agent.cli run `
  --route editorial_review.model="deepseek-ai/DeepSeek-V4-Pro" `
  --route editorial_review.provider="together" `
  --route final_polish.model="Qwen/Qwen3.6-35B-A3B" `
  --route final_polish.provider="deepinfra" `
  --show-events
```

Useful stage names:

```text
topic_angle_selection
research_synthesis
topic_brief
article_generation
editorial_review
revision
final_polish
featured_image
```

## Override routes with environment variables

For a stage named `editorial_review`, either naming style works:

```powershell
$env:HF_EDITORIAL_REVIEW_MODEL="deepseek-ai/DeepSeek-V4-Pro"
$env:HF_EDITORIAL_REVIEW_PROVIDER="together"
```

or:

```powershell
$env:HF_MODEL_EDITORIAL_REVIEW="deepseek-ai/DeepSeek-V4-Pro"
$env:HF_PROVIDER_EDITORIAL_REVIEW="together"
```

## Use a different routing file

```powershell
python -m editorial_agent.cli run `
  --model-routing-file ".\config\my_experiment_routes.yaml" `
  --print-model-routing `
  --show-events
```

The routing file can be YAML or JSON. The built-in YAML parser supports the simple mapping used in `config/model_routing.yaml`; PyYAML is not required.

## Legacy lane overrides still exist

The older heavy/small/image lane flags are still accepted:

```powershell
python -m editorial_agent.cli run `
  --text-model "openai/gpt-oss-120b" `
  --text-provider "together" `
  --small-text-model "Qwen/Qwen3.6-35B-A3B" `
  --small-text-provider "deepinfra" `
  --image-model "black-forest-labs/FLUX.1-Krea-dev" `
  --image-provider "fal-ai"
```

However, if `config/model_routing.yaml` exists, per-stage routing is preferred. Use the routing file or `--route` for precise control.

## Why not use the heavy model everywhere?

The project optimizes for article quality without unnecessary token spend.

Cheaper model calls are used where the expected output is short or structured:

- topic/angle selection;
- final polish;
- some metadata repair.

Stronger or more critical models are used where model judgment matters most:

- research synthesis;
- editorial review;
- topic brief;
- full article package;
- full revision when review gates fail.

## Why deterministic code still matters

The model is not allowed to own these controls:

- WordPress acceptance gating;
- draft-only publishing status;
- live-site scraping;
- duplicate-risk thresholds;
- source inventory;
- required-section validation;
- file writes;
- event logging;
- prompt budget reporting.

The model assists editorial judgment. Python retains authority over side effects, gates, artifacts, and validations.
