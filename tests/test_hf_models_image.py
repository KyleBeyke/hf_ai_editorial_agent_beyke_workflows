from pathlib import Path

from PIL import Image, ImageDraw

from editorial_agent.hf_models import apply_deterministic_featured_image_cleanup, normalize_image_model_id


def test_normalize_image_model_id_strips_provider_policy_suffix():
    assert normalize_image_model_id("black-forest-labs/FLUX.1-Krea-dev:cheapest") == "black-forest-labs/FLUX.1-Krea-dev"
    assert normalize_image_model_id("black-forest-labs/FLUX.1-Krea-dev:fastest") == "black-forest-labs/FLUX.1-Krea-dev"
    assert normalize_image_model_id("black-forest-labs/FLUX.1-Krea-dev:preferred") == "black-forest-labs/FLUX.1-Krea-dev"


def test_normalize_image_model_id_keeps_plain_model():
    assert normalize_image_model_id("black-forest-labs/FLUX.1-Krea-dev") == "black-forest-labs/FLUX.1-Krea-dev"


def test_apply_deterministic_featured_image_cleanup_preserves_size_and_updates_file(tmp_path: Path):
    path = tmp_path / "image.webp"
    img = Image.new("RGB", (1344, 768), color=(30, 40, 60))
    draw = ImageDraw.Draw(img)
    # Simulate busy screen-text band.
    for y in range(330, 520, 12):
        draw.line((80, y, 1260, y), fill=(220, 220, 220), width=2)
    img.save(path)

    before = path.read_bytes()
    apply_deterministic_featured_image_cleanup(path)
    after = path.read_bytes()
    out = Image.open(path)

    assert out.size == (1344, 768)
    assert before != after
