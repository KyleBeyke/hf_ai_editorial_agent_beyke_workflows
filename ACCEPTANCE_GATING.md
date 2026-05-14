# Acceptance Gating

This project is intentionally designed so the editorial agent cannot publish on
its own.

## Non-negotiable controls

- `run` never calls WordPress.
- `prepare-publish` only writes `publish_request.json`.
- `publish_request.json` is created with `approved=false`.
- `publish-draft` refuses to run unless `--human-approved` is passed.
- `publish-draft` also refuses unless the approval file contains:
  - `action=create_wordpress_draft`
  - `status=draft`
  - matching `run_dir`
  - `approved=true`
  - `approved_by`
  - `approved_at`
- The WordPress payload is forcibly set to `status=draft`.
- The generated article package must include `## Author` with `Kyle Beyke`.
- If `WP_AUTHOR_ID` is set, the WordPress payload includes that numeric author ID.
- If WordPress returns anything other than draft, the client raises an error.

## Human review artifacts

Before approving, review:

- `article.md`
- `featured_image.*`
- `claim_ledger.json`
- `fact_analysis_boundary.md`
- `duplicate_body_report.json`
- `image_validation.json`
- `run_report.json`
- `events.jsonl`

## Why this exists

Generating content and publishing content are different risk categories. The
agent may automate research, drafting, review, and packaging, but publication
requires human acceptance.
