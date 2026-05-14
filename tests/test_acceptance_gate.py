import json
from pathlib import Path

import pytest

from editorial_agent.wordpress import create_approval_request, create_wordpress_draft_with_gate


def test_publish_gate_rejects_unapproved_request(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "article.md").write_text("# Test\n\n## Slug\n\ntest\n", encoding="utf-8")
    (run_dir / "featured.webp").write_bytes(b"not-a-real-image-but-exists-for-gate-test")
    request = create_approval_request(run_dir)

    with pytest.raises(PermissionError):
        create_wordpress_draft_with_gate(run_dir, request, dry_run=True)


def test_publish_gate_allows_only_draft_after_human_acceptance(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "article.md").write_text("# Test Draft\n\n## Slug\n\ntest-draft\n\n## Excerpt\n\nExample excerpt.", encoding="utf-8")
    (run_dir / "featured.webp").write_bytes(b"not-a-real-image-but-exists-for-gate-test")
    request = create_approval_request(run_dir)
    payload = json.loads(request.read_text(encoding="utf-8"))
    payload.update({"approved": True, "approved_by": "human-editor", "approved_at": "2026-05-10T00:00:00Z"})
    approved = run_dir / "approved.json"
    approved.write_text(json.dumps(payload), encoding="utf-8")

    result = create_wordpress_draft_with_gate(run_dir, approved, dry_run=True)
    assert result["dry_run"] is True
    assert result["payload"]["status"] == "draft"


def test_publish_gate_requires_existing_featured_image(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "article.md").write_text("# Test Draft\n\n## Slug\n\ntest-draft\n", encoding="utf-8")
    request = create_approval_request(run_dir)
    payload = json.loads(request.read_text(encoding="utf-8"))
    payload.update({"approved": True, "approved_by": "human-editor", "approved_at": "2026-05-10T00:00:00Z"})
    approved = run_dir / "approved.json"
    approved.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PermissionError, match="featured_image"):
        create_wordpress_draft_with_gate(run_dir, approved, dry_run=True)
