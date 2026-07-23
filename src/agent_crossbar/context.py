"""Input artifact validation for sensitivity-constrained operations."""

from __future__ import annotations

from typing import Any


def validate_input_artifact(
    artifact: dict[str, Any],
    sensitivity: str = "normal",
) -> dict[str, Any]:
    """Validate a single input artifact against sensitivity rules.

    Returns a result dict with ``ok: bool`` and optional ``error``/``message``.

    In ``sensitivity="secret"`` mode, artifacts with ``sanitized=False`` are
    rejected.
    """
    sensitivity_val = sensitivity.lower() if sensitivity else "normal"

    if sensitivity_val == "secret" and not artifact.get("sanitized", False):
        return {
            "ok": False,
            "error": "unsanitized_artifact_in_secret_mode",
            "message": "Unsanitized input artifact rejected in secret mode. "
            "Set sanitized=true or use a sanitized artifact.",
        }

    return {
        "ok": True,
        "error": None,
        "message": "Artifact accepted",
    }
