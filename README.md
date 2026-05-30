# Hugging Face AI Editorial Agent for Beyke Workflows

A runnable Python editorial agent for **beykeworkflows.com**. It scouts recent AI topics, checks them against the configured AI writing archive, selects a non-duplicate editorial opportunity, gathers source evidence, creates a topic brief, drafts a WordPress-ready editorial article package authored by **Kyle Beyke**, reviews the draft, generates/validates a featured image, and prepares a human-gated WordPress draft request.

The agent is designed for correctness over false completion. It writes artifacts and review reports so a human can inspect what happened before anything touches WordPress.

## What it does

```text
Site Verification Agent
  -> scrape configured AI archive and verify possible internal links

Topic Scout Agent
  -> collect recent AI topics from RSS, arXiv, and Hacker News/Algolia

Candidate Selector Agent
  -> score recency, business relevance, technical relevance, and duplicate risk

Topic/Angle Selection Agent
  -> model-assisted judgment about interestingness, differentiation, thesis, and business consequences

Research Sufficiency Agent
  -> fetch evidence and decide whether there is enough source material

Research Synthesis Agent
  -> model-assisted synthesis of source claims, missing context, and claims to avoid

Topic Brief Agent
  -> generate the strategy brief using the bundled prompt

Article Writer Agent
  -> generate the full WordPress-ready article package using the bundled prompt

Editorial Review Agent
  -> independently review truthfulness, clarity, purpose, source use, and publication merit

Revision / Final Polish Agents
  -> ask the writer/polisher model for targeted help only when gates require it

Image Agent
  -> generate or locally fall back to a featured image, then validate the artifact

WordPress Acceptance Gate
  -> prepare a draft request, but never publish or create a draft without explicit human approval
```

## Current publication defaults

| Setting | Default |
|---|---|
| Site name | `Beyke Workflows` |
| Site base URL | `https://beykeworkflows.com` |
| AI archive/category URL | `https://beykeworkflows.com/category/writing/tech/ai/` |
| Required author metadata | `Kyle Beyke` |
| WordPress status | Always forced to `draft` |

All of these can be overridden by CLI flags or environment variables.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

On macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

## Configure

Copy `.env.example` to `.env` and fill in only the values you need.

```env
HF_TOKEN=
WP_BASE_URL=https://beykeworkflows.com
WP_USERNAME=
WP_APP_PASSWORD=
WP_AUTHOR_ID=
AUTHOR_NAME=Kyle Beyke
SITE_NAME=Beyke Workflows
SITE_BASE_URL=https://beykeworkflows.com
SITE_CATEGORY_URL=https://beykeworkflows.com/category/writing/tech/ai/
```

`WP_AUTHOR_ID` is optional but recommended if the WordPress REST API user is not the same account that should appear as the post author. If set, it must be the numeric WordPress user ID for Kyle Beyke.

## Offline verification run

Offline mode makes no Hugging Face or WordPress calls. It uses deterministic fixtures and a local placeholder image.

```powershell
python -m editorial_agent.cli run --offline --output-dir outputs --show-events --print-model-routing
```

Expected key artifacts:

```text
article.md
topic_brief.md
research.json
candidate_scores.json
site_articles.json
events.jsonl
run_report.json
claim_ledger.json
fact_analysis_boundary.md
duplicate_body_report.json
model_editorial_review.json
final_polish_report.json
featured_image_prompt.txt
featured_image.*
image_validation.json
publish_request.json
```

## Live draft-generation run

```powershell
python -m editorial_agent.cli run `
  --output-dir outputs `
  --site-url "https://beykeworkflows.com/category/writing/tech/ai/" `
  --site-base-url "https://beykeworkflows.com" `
  --site-name "Beyke Workflows" `
  --author-name "Kyle Beyke" `
  --show-events
```

The `run` command never writes to WordPress. It only writes local artifacts and a `publish_request.json` with `approved=false`.

## Human-gated WordPress draft creation

1. Review the generated artifacts.
2. Edit `publish_request.json`:
   - `approved=true`
   - `approved_by="Kyle Beyke"` or the reviewer name
   - `approved_at="2026-05-13T00:00:00Z"` or the actual approval timestamp
3. Create a draft only after explicit approval:

```powershell
python -m editorial_agent.cli publish-draft `
  --run-dir ".\outputs\run-..." `
  --approval-file ".\outputs\run-...\publish_request.json" `
  --human-approved
```

Dry run:

```powershell
python -m editorial_agent.cli publish-draft `
  --run-dir ".\outputs\run-..." `
  --approval-file ".\outputs\run-...\publish_request.json" `
  --human-approved `
  --dry-run
```

Safety controls:

- `run` never calls WordPress.
- `publish_request.json` starts with `approved=false`.
- `publish-draft` requires both a valid approval file and `--human-approved`.
- Payload status is forcibly set to `draft`.
- If WordPress returns a non-draft status, the client raises an error.

## Per-stage model routing

Routes live in `config/model_routing.yaml` and can be overridden without editing Python.

```powershell
python -m editorial_agent.cli run --offline --print-model-routing
```

Default stages:

| Stage | Purpose |
|---|---|
| `topic_angle_selection` | Select a differentiated topic/angle from candidates. |
| `research_synthesis` | Ask another model to identify important source claims and gaps. |
| `topic_brief` | Generate the strategy brief. |
| `article_generation` | Generate the WordPress-ready article package. |
| `editorial_review` | Ask a separate model to critique the draft. |
| `revision` | Ask the writer model to repair issues when needed. |
| `final_polish` | Ask a smaller model to repair metadata/style when needed. |
| `featured_image` | Generate the featured image. |

This is the model-collaboration path: models do not publish or control gates, but they can hand targeted feedback to later models when a quality gate needs help.

## Quality gates

Deterministic checks run before delivery:

- required Markdown package sections;
- `## Author` must identify Kyle Beyke (case-insensitive with flexible whitespace handling);
- focus keyword in metadata and image alt text (using word boundary matching to prevent false positives);
- article body length (configurable minimum word count, default 1500 words);
- source inventory consistency;
- related internal links must come from the configured archive scrape/fixture (standardized on current heading format);
- claim ledger and fact/analysis boundary artifacts;
- style review for generic AI/corporate phrases;
- full-body duplicate-risk report;
- image file and metadata validation.

## Security enhancements

The agent now includes several security improvements:

- Enhanced WordPress credential handling with input validation and secure error reporting
- Environment variable validation for all required credentials
- Retry logic with exponential backoff for network operations
- Improved exception handling with specific error types instead of broad exceptions
- Detailed security best practices documentation in `SECURITY.md`

See `SECURITY.md` for detailed security guidance and best practices.

## Development

```powershell
python -m compileall -q editorial_agent
python -m pytest -q
```

## Repository hygiene

Generated local artifacts are ignored by `.gitignore`:

```text
outputs/
_cache/
_editorial_memory/
.pytest_cache/
__pycache__/
.env
```

## Verification status

See `VALIDATION.md` for the most recent checks run in this environment. Live Hugging Face and live WordPress calls require credentials and were intentionally not run here.

## Repository readiness

Before pushing changes to GitHub, run the same checks used by CI:

```bash
python -m pip install -e ".[test]"
python -m compileall -q editorial_agent
python -m pytest -q
python -m pip wheel . --no-deps --no-build-isolation --wheel-dir dist
python -m editorial_agent.cli run --offline --output-dir outputs
python -m editorial_agent.cli review --run-dir <latest-run-dir>
```

Runtime prompt and routing resources are packaged under
`editorial_agent/prompts/` and `editorial_agent/config/`, so editable and
wheel installs use the same files. See `HANDOFF.md` for the maintainer
checklist and publishing safety model.
