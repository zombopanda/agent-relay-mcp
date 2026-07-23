"""ChatGPT Pro GUI adapter."""

from __future__ import annotations

from ..profiles.chatgpt_pro import SUPPORT_TIER
from .base import StaticAdapter


class ChatgptProAdapter(StaticAdapter):
    def __init__(self) -> None:
        super().__init__(
            name="chatgpt_pro",
            support_tier=SUPPORT_TIER,
            backend="gui",
            supports_interactive=False,
            effort_map={},
        )


adapter = ChatgptProAdapter()
