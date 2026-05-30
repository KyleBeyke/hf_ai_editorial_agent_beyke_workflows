#!/usr/bin/env python3
"""Test script to verify improvements."""

import re
import sys
import os

# Add the current directory to the path so we can import editorial_agent
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from editorial_agent.validation import validate_article_package


def test_placeholder_validation():
    """Test improved placeholder validation."""
    print("Testing placeholder validation...")

    # Test with placeholder in code block (should pass)
    markdown_with_code = """
## Title
Test Article

## Author
Kyle Beyke

## Focus Keyword
AI

## Article Body
This is a test article with code:

```
[PASTE content here]
```

More content here.
"""

    result = validate_article_package(markdown_with_code)
    placeholder_issues = [issue for issue in result.issues if "unresolved placeholders" in issue]
    print(f"Placeholder in code block - Issues: {len(placeholder_issues)}")

    # Test with placeholder outside code block (should fail)
    markdown_with_placeholder = """
## Title
Test Article

## Author
Kyle Beyke

## Focus Keyword
AI

## Article Body
This is a test article with [PASTE content here] which should fail.
"""

    result = validate_article_package(markdown_with_placeholder)
    placeholder_issues = [issue for issue in result.issues if "unresolved placeholders" in issue]
    print(f"Placeholder outside code block - Issues: {len(placeholder_issues)} (expected: 1)")


def test_author_validation():
    """Test improved author validation."""
    print("\nTesting author validation...")

    base_markdown = """
## Title
Test Article

## Focus Keyword
AI

## Article Body
This is a test article.
"""

    # Test case insensitive author
    markdown = base_markdown.replace("## Focus Keyword", "## Author\nkyle beyke\n\n## Focus Keyword")
    result = validate_article_package(markdown)
    author_issues = [issue for issue in result.issues if "Author section must identify Kyle Beyke" in issue]
    print(f"Lowercase author - Issues: {len(author_issues)} (expected: 0)")


def test_configurable_validation():
    """Test configurable validation parameters."""
    print("\nTesting configurable validation...")

    short_article = """
## Title
Test Article

## Author
Kyle Beyke

## Focus Keyword
AI

## Slug
test-article

## Meta Description
Test meta description

## Excerpt
Test excerpt

## Tags
test

## Consolidated WordPress Content Block

## Article Body
This is a short article with just a few words to test the validation.

## Key Takeaways
- Takeaway 1

## Sources
- Source 1

## Related articles from Beyke Workflows
- Related 1

## Jetpack Social Message
Social message

## Compliance Check
Compliance check

## Featured Image Filename Suggestion
test.png

## Featured Image Alt Text
Test alt text

## Featured Image Title
Test title

## Featured Image Caption
Test caption

## Featured Image Description
Test description
"""

    # Test with default minimum
    result = validate_article_package(short_article, min_word_count=1500)
    word_issues = [issue for issue in result.issues if "too short" in issue]
    print(f"Short article with 1500 min - Issues: {len(word_issues)} (expected: 1), Word count: {result.article_word_count}")

    # Test with low minimum
    result = validate_article_package(short_article, min_word_count=5)
    word_issues = [issue for issue in result.issues if "too short" in issue]
    print(f"Short article with 5 min - Issues: {len(word_issues)} (expected: 0), Word count: {result.article_word_count}")


if __name__ == "__main__":
    test_placeholder_validation()
    test_author_validation()
    test_configurable_validation()
    print("\nAll tests completed!")