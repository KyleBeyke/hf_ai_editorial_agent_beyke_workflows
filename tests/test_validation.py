from editorial_agent.hf_models import offline_article_package
from editorial_agent.validation import validate_article_package


def test_offline_article_package_passes_basic_validation():
    md = offline_article_package("test")
    result = validate_article_package(md)
    assert result.ok, result.issues
    assert result.article_word_count >= 1500
    assert result.focus_keyword == "AI agent reliability"
