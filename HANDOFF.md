# Handoff Guide

This repository contains a Python editorial-agent package that creates a
reviewed, human-gated WordPress draft package for Beyke Workflows AI content.

## Maintainer checklist

1. Create a virtual environment.
2. Install with `python -m pip install -e ".[test]"`.
3. Run `python -m compileall -q editorial_agent`.
4. Run `python -m pytest -q`.
5. Run `python -m pip wheel . --no-deps --no-build-isolation --wheel-dir dist`.
6. Run an offline end-to-end check:
   `python -m editorial_agent.cli run --offline --output-dir outputs`.
7. Run `python -m editorial_agent.cli review --run-dir <latest-run-dir>`.
8. Review `publish_request.json`, `article.md`, `image_validation.json`, and
   `review_report.json` before any WordPress draft action.

## Security considerations

The agent now includes enhanced security features:

- WordPress credentials are validated and handled securely with sanitized error messages
- Environment variables are validated before use
- Network operations include retry logic with exponential backoff
- Specific exception handling replaces broad exception catching
- See `SECURITY.md` for detailed security best practices

## Runtime resources

Prompt templates and model-routing configuration are packaged under:

- `editorial_agent/prompts/`
- `editorial_agent/config/`

The top-level `prompts/` and `config/` directories are kept as editable
source copies for review. Runtime code loads the packaged copies so wheel
installs and editable installs behave the same way.

## Runtime resources

Prompt templates and model-routing configuration are packaged under:

- `editorial_agent/prompts/`
- `editorial_agent/config/`

The top-level `prompts/` and `config/` directories are kept as editable
source copies for review. Runtime code loads the packaged copies so wheel
installs and editable installs behave the same way.

## Publishing safety model

The agent never publishes directly. It can only create a WordPress post with
status `draft`, and only through the `publish-draft` command after all of the
following are true:

- a human-edited approval file has `approved=true`;
- `approved_by` and `approved_at` are populated;
- the approval file points at the requested run directory;
- the article file exists;
- the featured image file exists;
- the CLI call includes `--human-approved`.

`--dry-run` validates the same gate and writes the WordPress payload without
contacting WordPress.

## Image handling

Featured-image discovery supports `.png`, `.jpg`, `.jpeg`, and `.webp`.
Extension and MIME-type handling live in `editorial_agent/image_files.py` so
review, approval, and WordPress upload behavior stay consistent.

## Environment variables

Copy `.env.example` to `.env` for local runs. Required live WordPress draft
variables are:

- `WP_BASE_URL`
- `WP_USERNAME`
- `WP_APP_PASSWORD`

Optional but recommended:

- `WP_AUTHOR_ID`
- `HF_TOKEN`
- model/provider overrides documented in `MODEL_SELECTION.md`
