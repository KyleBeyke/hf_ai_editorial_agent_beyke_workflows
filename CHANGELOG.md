# Changelog

## 0.7.0 - Security and Validation Enhancements

- Enhanced WordPress credential security with input validation and secure error handling
- Improved validation accuracy with case-insensitive author matching and word boundary focus keyword validation
- Added configurable minimum article word count (default 1500 words)
- Enhanced placeholder validation to ignore placeholders in code blocks
- Standardized related articles validation on current heading format
- Improved error handling with specific exception types instead of broad exceptions
- Added retry logic with exponential backoff for network operations
- Enhanced payload validation for WordPress API calls
- Expanded security documentation with detailed best practices
- Added comprehensive test coverage for security and validation improvements

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
