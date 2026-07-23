"""OpenCode profile constants and entry."""

from __future__ import annotations

# Single source of truth for this provider's support tier — the adapter
# module re-exports this constant rather than hardcoding its own literal.
SUPPORT_TIER = "supported"

OPENCODE_PROVIDER_ID = "opencode-go"
OPENCODE_DEFAULT_MODEL = "opencode/deepseek-v4-flash-free"
OPENCODE_MODELS = [
    OPENCODE_DEFAULT_MODEL,
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "glm-5.1",
    "glm-5.2",
    "kimi-k2.6",
    "kimi-k2.7-code",
    "mimo-v2.5",
    "mimo-v2.5-pro",
    "minimax-m2.7",
    "minimax-m3",
]


def build_entry() -> dict:
    return {
        "aliases": [],
        "models": OPENCODE_MODELS,
        "default_model": OPENCODE_DEFAULT_MODEL,
        "operations": ["review", "text", "advice", "dev"],
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
        "billing_mode": "free_defaults",
        "job_send_supported": False,
    }
