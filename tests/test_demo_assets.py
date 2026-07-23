"""Release checks for the bidirectional Ghostty demo artifact."""

from __future__ import annotations

import json
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1]
DEMO_DIR = PACKAGE_DIR / "demo"


def _gif_duration_seconds(data: bytes) -> float:
    """Sum GIF graphic-control delays without adding an image dependency."""
    total_centiseconds = 0
    offset = 0
    marker = b"\x21\xf9\x04"
    while (offset := data.find(marker, offset)) != -1:
        total_centiseconds += int.from_bytes(data[offset + 4 : offset + 6], "little")
        offset += len(marker)
    return total_centiseconds / 100


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


def test_demo_gif_is_present_and_bounded_for_readme():
    metadata = json.loads((DEMO_DIR / "metadata.json").read_text())
    gif = DEMO_DIR / metadata["asset"]
    assert gif.exists(), "record the real Ghostty demo before release"
    data = gif.read_bytes()
    assert data.startswith((b"GIF87a", b"GIF89a"))
    assert 100_000 <= len(data) <= 15_000_000
    duration = _gif_duration_seconds(data)
    assert metadata["duration_seconds_min"] <= duration <= metadata["duration_seconds_max"]
    assert b"/Users/" not in data
    assert b"git" + b".home" not in data
    assert b"pandenko" not in data.lower()
