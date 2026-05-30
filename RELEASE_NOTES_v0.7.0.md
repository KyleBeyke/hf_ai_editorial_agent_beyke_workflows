# HF AI Editorial Agent v0.7.0 Release Notes

## Overview

Version 0.7.0 of the HF AI Editorial Agent introduces significant security enhancements, validation improvements, and reliability fixes. This release focuses on making the agent more secure, accurate, and robust while maintaining full backward compatibility.

## Key Improvements

### Security Enhancements

- **WordPress Credential Security**: Enhanced credential handling with input validation and secure error reporting to prevent credential exposure in logs
- **Environment Variable Validation**: Added comprehensive validation for all required environment variables
- **Payload Validation**: Improved validation for WordPress API payloads with size limits and format checking
- **URL Validation**: Added validation for WordPress base URL format
- **Enhanced Security Documentation**: Expanded `SECURITY.md` with detailed best practices for WordPress, Hugging Face, and general security

### Validation Accuracy Improvements

- **Placeholder Detection**: Enhanced placeholder validation to ignore placeholders inside code blocks, reducing false positives
- **Author Validation**: Added case-insensitive matching with flexible whitespace handling for author names
- **Focus Keyword Validation**: Implemented word boundary matching to prevent partial keyword matches from causing false positives
- **Configurable Article Length**: Made minimum article word count configurable through `AgentConfig` (default remains 1500 words)
- **Related Articles Validation**: Standardized on current heading format and removed legacy heading support for consistency

### Reliability and Performance

- **Retry Logic**: Added exponential backoff retry logic to WordPress operations, web scraping, and other network operations
- **Targeted Exception Handling**: Replaced broad `except Exception` with specific exception types for better error diagnosis
- **Improved Error Recovery**: Enhanced error handling with better retry mechanisms and detailed error reporting

### Testing and Documentation

- **Enhanced Test Coverage**: Added new tests for security improvements and validation enhancements
- **Updated Documentation**: Comprehensive updates to README, CHANGELOG, and HANDOFF documentation
- **Security Best Practices**: Detailed security guidance in `SECURITY.md`

## Technical Details

### Breaking Changes

- None. Full backward compatibility is maintained.

### Configuration Changes

- Added `min_article_word_count` parameter to `AgentConfig` (default: 1500)
- WordPress URL validation now requires `http://` or `https://` prefix

### API Changes

- `validate_article_package()` now accepts an optional `min_word_count` parameter
- WordPress client constructors now validate URL format

### Dependency Changes

- No new dependencies added
- Existing dependencies remain the same

## Upgrade Instructions

For existing users, upgrading to v0.7.0 requires no code changes. Simply update the package:

```bash
pip install --upgrade hf-ai-editorial-agent
```

Or if installing from source:

```bash
git pull
python -m pip install -e .
```

## Files Modified

- `editorial_agent/wordpress.py` - Enhanced security and validation
- `editorial_agent/validation.py` - Improved validation accuracy
- `editorial_agent/schemas.py` - Added configurable validation parameters
- `editorial_agent/scrapers.py` - Added retry logic
- `editorial_agent/research.py` - Added retry logic
- `editorial_agent/duplicate_body.py` - Added retry logic
- `editorial_agent/model_judgment.py` - Improved exception handling
- `editorial_agent/claim_ledger.py` - Improved exception handling
- `editorial_agent/source_diversity.py` - Improved exception handling
- `editorial_agent/review.py` - Improved exception handling
- `editorial_agent/agent.py` - Updated validation calls
- `editorial_agent/cli.py` - Updated validation calls
- `tests/test_wordpress_security.py` - New security tests
- `tests/test_validation_improvements.py` - New validation tests
- `README.md` - Updated documentation
- `CHANGELOG.md` - Updated changelog
- `HANDOFF.md` - Updated documentation
- `SECURITY.md` - Enhanced security guidance
- `pyproject.toml` - Version bump to 0.7.0

## Testing

All existing tests continue to pass. New tests have been added to verify:

- WordPress credential security improvements
- Validation accuracy enhancements
- Retry logic functionality
- Exception handling improvements

Run the test suite with:

```bash
python -m pytest
```

## Support

For issues or questions about this release, please open an issue on the GitHub repository or contact the maintainers.