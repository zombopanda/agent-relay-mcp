"""Provider adapter contract and discovery tests."""

from __future__ import annotations

from agent_crossbar.adapters import registry
from agent_crossbar.adapters.base import normalize_effort
from agent_crossbar.adapters.codex import parse_model_list_response
from agent_crossbar.adapters.opencode import parse_models_output


def test_every_public_profile_has_its_own_adapter_module() -> None:
    assert set(registry.ADAPTERS) == {
        "chatgpt_pro",
        "claude",
        "codex",
        "opencode",
        "reasonix",
    }
    assert all(
        adapter.__class__.__module__.split(".")[-1] == name
        for name, adapter in registry.ADAPTERS.items()
    )


def test_opencode_models_are_parsed_from_cli_output() -> None:
    result = parse_models_output(
        "opencode-go/glm-5.2\nanthropic/claude-opus-4-8\nopencode-go/deepseek-v4-pro\n"
    )

    assert result == [
        "opencode-go/glm-5.2",
        "anthropic/claude-opus-4-8",
        "opencode-go/deepseek-v4-pro",
    ]


def test_opencode_models_accepts_colon_tags() -> None:
    """parse_models_output must accept model IDs with colon tags."""
    from agent_crossbar.adapters.opencode import parse_models_output

    result = parse_models_output(
        "openrouter/cohere/north-mini-code:free\n"
        "openrouter/qwen/qwen-plus-2025-07-28:thinking\n"
        "openrouter/meta-llama/llama-4-maverick:free\n"
        "https://evil.com/v1/not-a-model\n"
        "not/a/model/with spaces\n"
    )

    assert result == [
        "openrouter/cohere/north-mini-code:free",
        "openrouter/qwen/qwen-plus-2025-07-28:thinking",
        "openrouter/meta-llama/llama-4-maverick:free",
    ], f"Colon-tagged IDs must be accepted, URLs and malformed rejected, got: {result}"


def test_codex_models_and_efforts_are_parsed_from_app_server() -> None:
    result = parse_model_list_response(
        {
            "data": [
                {
                    "id": "gpt-5.6-sol",
                    "model": "gpt-5.6-sol",
                    "hidden": False,
                    "isDefault": True,
                    "defaultReasoningEffort": "medium",
                    "supportedReasoningEfforts": [
                        {"reasoningEffort": "low", "description": ""},
                        {"reasoningEffort": "medium", "description": ""},
                        {"reasoningEffort": "high", "description": ""},
                        {"reasoningEffort": "xhigh", "description": ""},
                    ],
                },
                {
                    "id": "hidden-model",
                    "model": "hidden-model",
                    "hidden": True,
                    "isDefault": False,
                    "defaultReasoningEffort": "medium",
                    "supportedReasoningEfforts": [],
                },
            ]
        }
    )

    assert result.models == ("gpt-5.6-sol",)
    assert result.default_model == "gpt-5.6-sol"
    assert result.native_efforts == ("low", "medium", "high", "xhigh")


def test_shared_effort_maps_max_to_provider_native_value() -> None:
    assert normalize_effort("max", {"max": "xhigh"}) == "xhigh"
    assert normalize_effort("high", {"high": "high"}) == "high"


# ── Single source of truth for support_tier ─────────────────────────────────

EXPECTED_TIERS = {
    "codex": "supported",
    "claude": "supported",
    "opencode": "supported",
    "reasonix": "experimental",
    "chatgpt_pro": "experimental",
}


def test_adapter_support_tier_matches_profile_registry() -> None:
    """Adapter support_tier must never diverge from the profiles registry.

    Regression: adapters/chatgpt_pro.py hardcoded 'supported' while
    profiles/chatgpt_pro.py (the intended source of truth) said
    'experimental' — doctor/profile_health surfaced the wrong tier.
    """
    from agent_crossbar.profiles import PROFILE_REGISTRY, PROVIDER_SUPPORT_MATRIX

    for name, adapter in registry.ADAPTERS.items():
        assert adapter.support_tier == PROFILE_REGISTRY[name]["support_tier"], (
            f"{name}: adapter.support_tier={adapter.support_tier!r} != "
            f"PROFILE_REGISTRY tier={PROFILE_REGISTRY[name]['support_tier']!r}"
        )
        assert adapter.support_tier == PROVIDER_SUPPORT_MATRIX[name]["support_tier"], (
            f"{name}: adapter.support_tier={adapter.support_tier!r} != "
            f"PROVIDER_SUPPORT_MATRIX tier={PROVIDER_SUPPORT_MATRIX[name]['support_tier']!r}"
        )


def test_expected_tiers_per_provider() -> None:
    """Codex/Claude/OpenCode are supported; Reasonix/ChatGPT Pro are experimental."""
    for name, expected in EXPECTED_TIERS.items():
        assert registry.ADAPTERS[name].support_tier == expected, (
            f"{name}: expected tier {expected!r}, got {registry.ADAPTERS[name].support_tier!r}"
        )
