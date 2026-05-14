# Changelog

## 0.6.0 - Beyke Workflows GitHub-ready refresh

- Retargeted default publication site from legacy Kyle Beyke domain assumptions to `https://beykeworkflows.com`.
- Added explicit Kyle Beyke authorship requirements and validation.
- Added configurable site profile defaults for author, site name, base URL, and AI archive URL.
- Updated bundled topic-brief and article-generation prompts to match the current editorial workflow expectations.
- Updated Markdown package validation for the newer WordPress-ready content block structure.
- Added optional `WP_AUTHOR_ID` support for WordPress REST API draft payloads.
- Preserved human approval gating and forced WordPress draft status.
- Added repository hygiene files: `.gitignore`, `.env.example`, `LICENSE`, and validation documentation.
- Removed generated cache artifacts and stray leading backslash characters from source/script files.
