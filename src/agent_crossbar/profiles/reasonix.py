"""Reasonix profile constants and entry."""

from __future__ import annotations

# Single source of truth for this provider's support tier — the adapter
# module re-exports this constant rather than hardcoding its own literal.
SUPPORT_TIER = "experimental"

REASONIX_MODELS = ["deepseek-v4-flash", "deepseek-v4-pro"]


def build_entry() -> dict:
    return {
        "aliases": ["deepseek"],
        "models": REASONIX_MODELS,
        "operations": ["review", "text", "advice", "dev"],
        "interactive": True,
        "support_tier": SUPPORT_TIER,
    }


def build_matrix_entry() -> dict:
    entry = build_entry()
    return {
        "support_tier": entry["support_tier"],
        "os": ["darwin", "linux"],
        "operations": entry["operations"],
        "backend": "tmux",
        "interaction_modes": ["noninteractive", "interactive"],
        "effort_support": True,
        "billing_mode": "api",
        "job_send_supported": True,
    }
