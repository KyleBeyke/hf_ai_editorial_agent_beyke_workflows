from editorial_agent.hf_models import normalize_image_model_id


def test_normalize_image_model_id_strips_provider_policy_suffix():
    assert normalize_image_model_id("black-forest-labs/FLUX.1-Krea-dev:cheapest") == "black-forest-labs/FLUX.1-Krea-dev"
    assert normalize_image_model_id("black-forest-labs/FLUX.1-Krea-dev:fastest") == "black-forest-labs/FLUX.1-Krea-dev"
    assert normalize_image_model_id("black-forest-labs/FLUX.1-Krea-dev:preferred") == "black-forest-labs/FLUX.1-Krea-dev"


def test_normalize_image_model_id_keeps_plain_model():
    assert normalize_image_model_id("black-forest-labs/FLUX.1-Krea-dev") == "black-forest-labs/FLUX.1-Krea-dev"
