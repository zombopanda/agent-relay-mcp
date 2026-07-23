"""Policy validation tests for Task 3: Secret Rules, Budget Rules, Full Local Validation."""

from agent_relay_mcp.validation import validate_start_request


def _base_request(profile: str, operation: str, **overrides):
    """Build a minimal valid request dict."""
    req = {
        "operation": operation,
        "profile": profile,
        "transport": "print",
        "autonomy": "read_only",
        "external_context": "allowed",
        "sensitivity": "normal",
        "prompt": "test prompt",
    }
    req.update(overrides)
    return req


# ---------------------------------------------------------------------------
# Secret + external_context=allowed requires sanitized_context_only=true
# ---------------------------------------------------------------------------


def test_edit_local_dev_with_tmux_is_accepted(tmp_path):
    """edit_local with dev+tmux passes for interactive profiles."""
    req = _base_request(
        profile="reasonix", operation="dev", transport="tmux", autonomy="edit_local"
    )
    result = validate_start_request(req, state_root=tmp_path)
    assert result["ok"] is True
    assert result["error"] is None


def test_edit_local_dev_with_print_is_accepted(tmp_path):
    """edit_local with dev+print passes (no transport×autonomy gating)."""
    req = _base_request(
        profile="reasonix", operation="dev", transport="print", autonomy="edit_local"
    )
    result = validate_start_request(req, state_root=tmp_path)
    assert result["ok"] is True
    assert result["error"] is None


def test_review_with_edit_local_is_accepted_for_reasonix(tmp_path):
    """Current minimal contract has no autonomy×operation gating — edit_local passes."""
    req = _base_request(profile="reasonix", operation="review", autonomy="edit_local")
    result = validate_start_request(req, state_root=tmp_path)
    assert result["ok"] is True
    assert result["error"] is None


def test_read_only_review_is_accepted(tmp_path):
    """read_only is the baseline default autonomy — review passes."""
    req = _base_request(profile="reasonix", operation="review", autonomy="read_only")
    result = validate_start_request(req, state_root=tmp_path)
    assert result["ok"] is True
    assert result["error"] is None


def test_unknown_autonomy_is_rejected(tmp_path):
    """Unknown autonomy values are rejected with invalid_autonomy."""
    req = _base_request(profile="reasonix", operation="review", autonomy="unknown_mode")
    result = validate_start_request(req, state_root=tmp_path)
    assert result["ok"] is False
    assert result["error"] == "invalid_autonomy"


# ---------------------------------------------------------------------------
# Unsanitized input artifact rejected in secret sanitized mode
# ---------------------------------------------------------------------------
def test_sanitized_input_artifact_accepted_in_secret_sanitized_mode(tmp_path):
    """In secret mode with sanitized_context_only=true, a sanitized input artifact should be accepted."""
    req = _base_request(profile="reasonix", operation="text", text_subtype="summarize")
    req["sensitivity"] = "secret"
    req["external_context"] = "allowed"
    req["sanitized_context_only"] = True
    req["input_artifacts"] = [{"path": "/tmp/redacted.log", "sanitized": True}]
    result = validate_start_request(req, state_root=tmp_path)
    assert result["ok"] is True
    assert result["error"] is None


def test_no_artifacts_in_secret_mode_passes(tmp_path):
    """No input artifacts in secret mode should pass without artifact validation errors."""
    req = _base_request(profile="reasonix", operation="text", text_subtype="summarize")
    req["sensitivity"] = "secret"
    req["external_context"] = "allowed"
    req["sanitized_context_only"] = True
    result = validate_start_request(req, state_root=tmp_path)
    assert result["ok"] is True
    assert result["error"] is None
