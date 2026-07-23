"""ChatGPT Pro profile entry — experimental, manual gate required."""

from __future__ import annotations

# Single source of truth for this provider's support tier — the adapter
# module re-exports this constant rather than hardcoding its own literal.
SUPPORT_TIER = "experimental"


def build_entry() -> dict:
    return {
        "aliases": [],
        "models": [],
        "default_model": None,
        "operations": ["review", "advice"],
        "interactive": False,
        "support_tier": SUPPORT_TIER,
    }


def build_matrix_entry() -> dict:
    entry = build_entry()
    return {
        "support_tier": entry["support_tier"],
        "os": ["darwin"],
        "operations": entry["operations"],
        "backend": "gui",
        "interaction_modes": ["noninteractive"],
        "default_model": entry["default_model"],
        "effort_support": False,
        "billing_mode": "subscription_quota",
        "job_send_supported": False,
    }
