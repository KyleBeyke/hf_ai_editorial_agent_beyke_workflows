import pytest

from editorial_agent.image_files import featured_image_candidates, first_featured_image, media_content_type


def test_featured_image_discovery_includes_webp(tmp_path):
    webp = tmp_path / "article-featured.webp"
    webp.write_bytes(b"fake-webp")
    assert featured_image_candidates(tmp_path) == [webp]
    assert first_featured_image(tmp_path) == webp


def test_media_content_type_supports_webp_and_rejects_unknown(tmp_path):
    assert media_content_type(tmp_path / "image.webp") == "image/webp"
    assert media_content_type(tmp_path / "image.png") == "image/png"
    with pytest.raises(ValueError, match="Unsupported featured image extension"):
        media_content_type(tmp_path / "image.gif")
