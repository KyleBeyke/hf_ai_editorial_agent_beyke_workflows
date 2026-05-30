import pytest
from pathlib import Path

from editorial_agent.wordpress import WordPressDraftClient, wp_auth_header


def test_wp_auth_header_validation():
    """Test that wp_auth_header validates inputs properly."""
    # Valid inputs should work
    header = wp_auth_header("testuser", "testpass")
    assert "Authorization" in header
    assert header["Authorization"].startswith("Basic ")

    # Empty inputs should raise ValueError
    with pytest.raises(ValueError, match="required"):
        wp_auth_header("", "testpass")
    
    with pytest.raises(ValueError, match="required"):
        wp_auth_header("testuser", "")
    
    with pytest.raises(ValueError, match="required"):
        wp_auth_header("", "")


def test_wordpress_client_validation():
    """Test that WordPressDraftClient validates inputs properly."""
    # Valid inputs should work
    client = WordPressDraftClient("https://example.com", "testuser", "testpass")
    assert client.base_url == "https://example.com"
    
    # Invalid URL should raise ValueError
    with pytest.raises(ValueError, match="must start with"):
        WordPressDraftClient("example.com", "testuser", "testpass")
    
    # Empty inputs should raise ValueError
    with pytest.raises(ValueError, match="required"):
        WordPressDraftClient("", "testuser", "testpass")
    
    with pytest.raises(ValueError, match="required"):
        WordPressDraftClient("https://example.com", "", "testpass")
    
    with pytest.raises(ValueError, match="required"):
        WordPressDraftClient("https://example.com", "testuser", "")


def test_wordpress_client_from_env_validation(monkeypatch):
    """Test that WordPressDraftClient.from_env validates environment variables."""
    # Missing variables should raise RuntimeError
    monkeypatch.delenv("WP_BASE_URL", raising=False)
    monkeypatch.delenv("WP_USERNAME", raising=False)
    monkeypatch.delenv("WP_APP_PASSWORD", raising=False)
    
    with pytest.raises(RuntimeError, match="Missing WordPress environment variables"):
        WordPressDraftClient.from_env()
    
    # Invalid URL format should raise ValueError
    monkeypatch.setenv("WP_BASE_URL", "example.com")
    monkeypatch.setenv("WP_USERNAME", "testuser")
    monkeypatch.setenv("WP_APP_PASSWORD", "testpass")
    
    with pytest.raises(ValueError, match="must start with"):
        WordPressDraftClient.from_env()


def test_wordpress_payload_validation():
    """Test that wordpress_payload_from_article validates inputs."""
    from editorial_agent.wordpress import wordpress_payload_from_article
    
    # Empty input should raise ValueError
    with pytest.raises(ValueError, match="required"):
        wordpress_payload_from_article("")
    
    with pytest.raises(ValueError, match="required"):
        wordpress_payload_from_article(None)
    
    # Non-string input should raise ValueError
    with pytest.raises(ValueError, match="required"):
        wordpress_payload_from_article(123)