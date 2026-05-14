# Run this from the project root after installing requirements.
# First set your Hugging Face token:
# $env:HF_TOKEN="hf_your_token_here"
#
# Optional publication defaults:
# $env:SITE_BASE_URL="https://beykeworkflows.com"
# $env:SITE_CATEGORY_URL="https://beykeworkflows.com/category/writing/tech/ai/"
# $env:AUTHOR_NAME="Kyle Beyke"
#
# Per-stage model/provider choices live in:
# .\config\model_routing.yaml
#
# To inspect resolved routes before spending tokens, add --print-model-routing.
# Temporary overrides can be passed with --route, for example:
# --route editorial_review.model="deepseek-ai/DeepSeek-V4-Pro"

python -m editorial_agent.cli run --show-events --print-model-routing
