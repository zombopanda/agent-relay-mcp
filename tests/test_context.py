"""Input artifact validation tests."""

from __future__ import annotations

from pathlib import Path

from agent_relay_mcp.context import validate_input_artifact


def test_secret_mode_requires_caller_context_only(tmp_path: Path):
    """validate_input_artifact rejects unsanitized artifact in secret mode."""
    test_file = tmp_path / "raw.log"
    test_file.write_text("some raw log\n")
    result = validate_input_artifact(
        {"path": str(test_file), "sanitized": False},
        sensitivity="secret",
    )
    assert result["ok"] is False


def test_validate_input_artifact_accepts_sanitized_in_secret_mode(tmp_path: Path):
    """Sanitized artifacts are accepted even in secret sensitivity."""
    test_file = tmp_path / "sanitized.txt"
    test_file.write_text("sanitized content\n")
    result = validate_input_artifact(
        {"path": str(test_file), "sanitized": True},
        sensitivity="secret",
    )
    assert result["ok"] is True


def test_validate_input_artifact_accepts_normal_sensitivity(tmp_path: Path):
    """Non-secret sensitivity accepts unsanitized artifacts."""
    test_file = tmp_path / "code.py"
    test_file.write_text("def x(): pass\n")
    result = validate_input_artifact(
        {"path": str(test_file), "sanitized": False},
        sensitivity="normal",
    )
    assert result["ok"] is True
