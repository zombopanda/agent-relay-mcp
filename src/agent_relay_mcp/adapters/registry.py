"""Provider adapter registry."""

from __future__ import annotations

from .base import ProviderAdapter
from .chatgpt_pro import adapter as chatgpt_pro
from .claude import adapter as claude
from .codex import adapter as codex
from .opencode import adapter as opencode
from .reasonix import adapter as reasonix

ADAPTERS: dict[str, ProviderAdapter] = {
    adapter.name: adapter for adapter in (chatgpt_pro, claude, codex, opencode, reasonix)
}


def get_adapter(name: str) -> ProviderAdapter:
    try:
        return ADAPTERS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown profile '{name}'") from exc
