"""Normalize and validate start requests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_crossbar.models import Autonomy, Operation, Sensitivity, Transport
from agent_crossbar.profiles import (
    CODEX_DEFAULT_EFFORT,
    CODEX_DEFAULT_MODEL,
    CODEX_EFFORT_ALIASES,
    CODEX_EFFORTS,
    allowed_models,
    profile_interactive,
    profile_operations,
    resolve_profile,
)

_REQUIRED_FIELDS = (
    "operation",
    "profile",
    "transport",
    "autonomy",
    "sensitivity",
)


def validate_start_request(
    req: dict[str, Any], state_root: Path | str | None = None
) -> dict[str, Any]:
    """Validate a start request dict and return a result dict.

    The result dict always contains:
      - ok: bool
      - error: str | None
      - message: str
      - warnings: list[str]
      - job_created: bool

    An unknown profile is rejected with error=="invalid_profile" and
    job_created==False — no job directory is created.
    """
    warnings: list[str] = []

    # Check required fields
    for field_name in _REQUIRED_FIELDS:
        if field_name not in req or req[field_name] is None:
            return {
                "ok": False,
                "error": "missing_required_field",
                "message": f"Required field '{field_name}' is missing",
                "warnings": warnings,
                "job_created": False,
            }

    # Resolve profile (aliases -> canonical)
    profile_raw: str = req["profile"]
    ok, resolved = resolve_profile(profile_raw)
    if not ok:
        return {
            "ok": False,
            "error": "invalid_profile",
            "message": f"Unknown profile '{profile_raw}'",
            "warnings": warnings,
            "job_created": False,
        }

    # Validate operation
    try:
        Operation(req["operation"])
    except ValueError:
        return {
            "ok": False,
            "error": "invalid_operation",
            "message": f"Unknown operation '{req['operation']}'",
            "warnings": warnings,
            "job_created": False,
        }

    # Validate transport
    try:
        Transport(req["transport"])
    except ValueError:
        return {
            "ok": False,
            "error": "invalid_transport",
            "message": f"Unknown transport '{req['transport']}'",
            "warnings": warnings,
            "job_created": False,
        }

    # Validate autonomy
    try:
        Autonomy(req["autonomy"])
    except ValueError:
        return {
            "ok": False,
            "error": "invalid_autonomy",
            "message": f"Unknown autonomy '{req['autonomy']}'",
            "warnings": warnings,
            "job_created": False,
        }

    # Validate sensitivity
    try:
        Sensitivity(req["sensitivity"])
    except ValueError:
        return {
            "ok": False,
            "error": "invalid_sensitivity",
            "message": f"Unknown sensitivity '{req['sensitivity']}'",
            "warnings": warnings,
            "job_created": False,
        }

    transport_val = Transport(req["transport"])
    operation_val = Operation(req["operation"])

    def fail(error: str, message: str) -> dict[str, Any]:
        return {
            "ok": False,
            "error": error,
            "message": message,
            "warnings": warnings,
            "job_created": False,
        }

    # Rule: operation must be supported by the profile.
    supported_ops = profile_operations(resolved)
    if operation_val.value not in supported_ops:
        return fail(
            "unsupported_operation",
            f"Profile '{resolved}' does not support operation '{operation_val.value}'",
        )

    if operation_val == Operation.ADVICE and not str(req.get("prompt", "")).strip():
        return fail("missing_required_field", "prompt is required for advice operations")

    # Rule: tmux transport requires interactive support.
    if transport_val == Transport.TMUX and not profile_interactive(resolved):
        return fail(
            "unsupported_transport",
            f"Profile '{resolved}' does not support interactive tmux transport",
        )

    normalized_model: str | None = None
    normalized_effort: str | None = None

    # Rule: reasonix review defaults to flash unless the caller asks for pro.
    if resolved == "reasonix" and operation_val == Operation.REVIEW:
        model = req.get("model") or "deepseek-v4-flash"
        models = allowed_models(resolved)
        if model not in models:
            return fail(
                "invalid_model", f"Model '{model}' is not supported for profile '{resolved}'"
            )
        req["model"] = model
        normalized_model = model

    if resolved == "claude":
        models = allowed_models(resolved)
        model = req.get("model")
        if model is None:
            model = profile_raw if profile_raw in models else models[0]
        if model not in models:
            return fail(
                "invalid_model", f"Model '{model}' is not supported for profile '{resolved}'"
            )
        req["model"] = model
        normalized_model = model

    if resolved == "codex":
        model = req.get("model") or CODEX_DEFAULT_MODEL
        if model not in allowed_models(resolved):
            return fail(
                "invalid_model", f"Model '{model}' is not supported for profile '{resolved}'"
            )
        effort = req.get("effort") or CODEX_DEFAULT_EFFORT
        effort = CODEX_EFFORT_ALIASES.get(effort, effort)
        if effort not in CODEX_EFFORTS:
            return fail(
                "invalid_effort", f"Effort '{effort}' is not supported for profile '{resolved}'"
            )
        req["model"] = model
        req["effort"] = effort
        normalized_model = model
        normalized_effort = effort

        # Rule: Codex effort must be supported by the selected model's discovered capabilities.
        if state_root is not None:
            from agent_crossbar.adapters.codex import adapter as codex_adapter
            from agent_crossbar.discovery import discover_profile_models

            try:
                catalog = discover_profile_models(
                    Path(state_root) if not isinstance(state_root, Path) else state_root, "codex"
                )
            except Exception:
                catalog = None
            err = codex_adapter.validate_effort_for_model(effort, catalog, model)
            if err is not None:
                return fail("unsupported_effort_for_model", err)

    # Rule: OpenCode validates against the live model catalog obtained via
    # discover_profile_models — which uses the cache when fresh and performs
    # a bounded live refresh only when missing or stale.  There is no static
    # allowlist fallback; a missing/error/empty catalog fails preflight.
    if resolved == "opencode":
        if state_root is None:
            return fail("discovery_error", "state_root is required for OpenCode model discovery")

        from agent_crossbar.adapters.opencode import adapter as opencode_adapter
        from agent_crossbar.discovery import discover_profile_models

        sr = Path(state_root) if not isinstance(state_root, Path) else state_root

        try:
            catalog = discover_profile_models(sr, "opencode")
        except Exception as exc:
            return fail("discovery_error", f"OpenCode model discovery failed: {exc}")

        if catalog.error:
            return fail("discovery_error", f"OpenCode model discovery failed: {catalog.error}")

        if not catalog.models:
            return fail("discovery_error", "No OpenCode models discovered")

        requested = req.get("model")
        if requested is None:
            model = catalog.default_model
            if model is None:
                return fail("discovery_error", "No default OpenCode model available")
        else:
            catalog_model_ids = set(catalog.models)
            if requested in catalog_model_ids:
                model = requested
            else:
                # Try suffix match: short name matches the part after
                # the last slash in a catalog model ID.
                matched = None
                for cid in catalog.models:
                    if "/" in cid and cid.split("/", 1)[1] == requested:
                        matched = cid
                        break
                if matched is not None:
                    model = matched
                else:
                    return fail(
                        "invalid_model",
                        f"Model '{requested}' is not available in OpenCode "
                        f"(discovered: {', '.join(catalog.models)})",
                    )

        req["model"] = model
        normalized_model = model

        # Validate effort against per-model discovery data
        effort = req.get("effort")
        if effort is not None:
            err = opencode_adapter.validate_effort_for_model(effort, catalog, model)
            if err is not None:
                return fail("unsupported_effort_for_model", err)
            normalized_effort = effort

    return {
        "ok": True,
        "error": None,
        "message": "Validation passed",
        "warnings": warnings,
        "job_created": True,
        "profile": resolved,
        "operation": req["operation"],
        "model": normalized_model,
        "effort": normalized_effort,
    }
