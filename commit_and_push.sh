#!/bin/bash

# Script to commit and push all changes with proper versioning

set -e  # Exit on any error

echo "Starting commit and push process for HF AI Editorial Agent v0.7.0"

# Check current git status
echo "Checking git status..."
git status

# Add all changed files
echo "Adding all changes to git..."
git add .

# Create commit with detailed message
echo "Creating commit..."
git commit -m "Release v0.7.0 - Security and Validation Enhancements

Enhanced Security Features:
- Improved WordPress credential handling with input validation and secure error reporting
- Environment variable validation for all required credentials
- Enhanced payload validation for WordPress API calls
- Expanded security documentation with detailed best practices

Improved Validation Accuracy:
- Enhanced placeholder validation to ignore placeholders in code blocks
- Case-insensitive author matching with flexible whitespace handling
- Word boundary matching for focus keyword validation to prevent false positives
- Configurable minimum article word count (default 1500 words)
- Standardized related articles validation on current heading format

Reliability Improvements:
- Added retry logic with exponential backoff for network operations
- Improved error handling with specific exception types instead of broad exceptions
- Enhanced error recovery mechanisms

Testing and Documentation:
- Added comprehensive test coverage for security and validation improvements
- Updated README, CHANGELOG, and HANDOFF documentation
- Expanded SECURITY.md with detailed best practices

Version bump from 0.6.0 to 0.7.0 in pyproject.toml"

# Create tag
echo "Creating tag v0.7.0..."
git tag -a v0.7.0 -m "Release v0.7.0 - Security and Validation Enhancements"

# Push to remote
echo "Pushing to remote repository..."
git push origin main
git push origin v0.7.0

echo "Successfully committed and pushed v0.7.0!"
echo "Changes include security enhancements, validation improvements, and reliability fixes."