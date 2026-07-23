"""Tiny deterministic fixture used by the bidirectional Agent Crossbar demo."""


def display_name(raw: str) -> str:
    """Normalize a user-provided display name."""
    return raw.strip() or "Anonymous"
