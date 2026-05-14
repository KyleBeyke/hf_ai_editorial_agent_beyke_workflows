# Validation Report

Date: 2026-05-13

## Scope

This validation was performed without live Hugging Face provider calls and without live WordPress writes. The verified path is the deterministic offline workflow plus the human-gated WordPress dry-run path.

Live Hugging Face generation, live web research, and live WordPress draft creation still require maintainer credentials and should be validated by the maintainer before first production use.

## Final checks run

| Check | Command | Observed result |
|---|---|---|
| ZIP hygiene | archive inspection | No unsafe paths, cache directories, `.pyc` files, `dist/`, or `build/` output included |
| Python compile check | `python -m compileall -q editorial_agent` | Exit code `0` |
| Test suite | `python -m pytest -q` | Exit code `0`; `19 passed` |
| Editable install dry run | `python -m pip install -e . --no-deps --dry-run --no-build-isolation` | Exit code `0` |
| Wheel build | `python -m pip wheel . --no-deps --no-build-isolation --wheel-dir <tmp>` | Exit code `0` |
| Wheel contents | wheel archive inspection | Packaged prompts and model-routing config present under `editorial_agent/` |
| Offline end-to-end run | `python -m editorial_agent.cli run --offline --output-dir <tmp> --print-model-routing` | Exit code `0` |
| Review command | `python -m editorial_agent.cli review --run-dir <run-dir>` | Exit code `0` |
| WordPress gate without human approval | `python -m editorial_agent.cli publish-draft --run-dir <run-dir> --approval-file <publish_request.json> --dry-run` | Correctly refused with exit code `3` |
| Approved WordPress dry-run | `python -m editorial_agent.cli publish-draft --run-dir <run-dir> --approval-file <approved_request.json> --human-approved --dry-run` | Exit code `0`; wrote `wordpress_draft_result.json` |
| Secret scan | token/password regex scan | No credible secrets found; only a false positive in help text |

The Python environment emitted unrelated `artifact_tool` spreadsheet warmup stderr during Python startup. These messages came from the surrounding execution environment, not this project, and the project commands above returned successful exit codes where indicated.

## Offline end-to-end result

The final offline run generated:

- `article.md`
- `.webp` featured image
- `topic_brief.md`
- `events.jsonl`
- `run_report.json`
- `publish_request.json`
- `image_validation.json`

Key observed results:

| Gate | Observed result |
|---|---|
| Article validation | `ok=True` |
| Focus keyword | `AI agent reliability` |
| Deterministic editorial review | `ok=True` |
| Style review | `ok=True` |
| Model editorial review | `deserves_publication_after_human_review=True` |
| Revision required | `False` |
| Final polish needed | `False` |
| Full-body duplicate check | `ok=True` |
| Image validation | `ok=True` |
| Image dimensions | `1344 x 768` |
| Publish request | Created with `approved=false`; no remote write performed |
| Publish request featured image | Non-null `.webp` path |

## Authorship and site targeting

Verified in the generated offline artifact:

- The article package includes `## Author` with `Kyle Beyke`.
- The default target site is `https://beykeworkflows.com`.
- The default AI archive/category URL is `https://beykeworkflows.com/category/writing/tech/ai/`.
- Internal related-link fixture URLs use `beykeworkflows.com`.
- `WP_AUTHOR_ID` is supported in the WordPress payload when set.
- The WordPress payload status is forcibly set to `draft`.

## Not verified

The following were intentionally not live-tested:

- Live Hugging Face text generation.
- Live Hugging Face image generation.
- Live scrape of `beykeworkflows.com`.
- Live SERP research.
- Live WordPress draft creation.
- WordPress category/tag/SEO-plugin field creation, because plugin-specific field names and WordPress term IDs were not provided.

## Manual pre-upload checklist

Before pushing publicly:

- Confirm the MIT license is the license Kyle Beyke wants.
- Confirm `WP_AUTHOR_ID` in `.env` maps to the Kyle Beyke WordPress user.
- Run one live non-publishing agent run with a valid `HF_TOKEN`.
- Review `article.md`, `claim_ledger.json`, `fact_analysis_boundary.md`, `duplicate_body_report.json`, and `image_validation.json`.
- Use `publish-draft --dry-run` before creating a real WordPress draft.
