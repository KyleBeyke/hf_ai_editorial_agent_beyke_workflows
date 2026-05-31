from editorial_agent.hf_models import offline_article_package
from editorial_agent.validation import validate_article_package


def test_offline_article_package_passes_basic_validation():
    md = offline_article_package("test")
    result = validate_article_package(md)
    assert result.ok, result.issues
    assert result.article_word_count >= 1500
    assert result.focus_keyword == "AI agent reliability"


def test_validation_accepts_bold_top_level_heading_labels():
    md = offline_article_package("test")
    md = md.replace("## Title", "**Title**").replace("## Author", "**Author**").replace("## Focus Keyword", "**Focus Keyword**")
    md = md.replace("AI agent reliability", "**AI agent reliability**", 1)
    result = validate_article_package(md)
    assert result.ok, result.issues
    assert result.focus_keyword == "AI agent reliability"


def test_validation_accepts_decision_framework_heading_variant():
    md = offline_article_package("test")
    md = md.replace("## Practical Decision Framework", "## Decision-Making Framework")
    result = validate_article_package(md)
    assert result.ok, result.issues
