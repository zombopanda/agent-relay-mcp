"""Release checks for the bidirectional Ghostty demo fixture."""

from __future__ import annotations

import json
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1]
DEMO_DIR = PACKAGE_DIR / "demo"


def test_demo_fixture_prompts_transcript_and_metadata_are_versioned():
    metadata = json.loads((DEMO_DIR / "metadata.json").read_text())
    assert metadata["fixture_version"] == "v1"
    assert metadata["product_version"] == "0.1.3"
    assert metadata["real_provider_output_required"] is True
    assert metadata["idle_acceleration_only"] is True
    assert metadata["directions"] == ["codex-to-claude", "claude-to-codex"]

    prompts = (DEMO_DIR / "PROMPTS.md").read_text()
    transcript = (DEMO_DIR / "TRANSCRIPT.md").read_text()
    fixture = (DEMO_DIR / "fixture" / "relay_demo.py").read_text()
    assert "CODEX → CLAUDE: PASS" in prompts
    assert "CLAUDE → CODEX: PASS" in prompts
    assert "Anonymous" in transcript
    assert 'or "Anonymous"' in fixture
