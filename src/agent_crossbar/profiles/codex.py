"""Codex profile constants and entry."""

from __future__ import annotations

# Single source of truth for this provider's support tier — the adapter
# module re-exports this constant rather than hardcoding its own literal.
SUPPORT_TIER = "supported"

CODEX_MODELS = ["gpt-5.6-sol", "gpt-5.6-terra"]
CODEX_EFFORTS = ["low", "medium", "high", "max"]
CODEX_EFFORT_ALIASES = {"light": "low"}
CODEX_DEFAULT_MODEL = "gpt-5.6-sol"
CODEX_DEFAULT_EFFORT = "medium"


def build_entry() -> dict:
    return {
        "aliases": [],
        "models": CODEX_MODELS,
        "default_model": CODEX_DEFAULT_MODEL,
        "operations": ["review", "text", "dev"],
        "interactive": False,
        "support_tier": SUPPORT_TIER,
    }


def build_matrix_entry() -> dict:
    entry = build_entry()
    return {
        "support_tier": entry["support_tier"],
        "os": ["darwin", "linux"],
        "operations": entry["operations"],
        "backend": "acp",
        "interaction_modes": ["noninteractive"],
        "default_model": entry["default_model"],
        "effort_support": True,
        "billing_mode": "subscription_quota",
        "job_send_supported": False,
    }
