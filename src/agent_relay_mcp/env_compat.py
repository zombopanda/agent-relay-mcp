"""Backward-compatible environment variable resolution.

Agent Relay MCP (v0.1.3) renamed from the internal ``agent-harness-mcp``.
The old ``AGENT_HARNESS_*`` env var names still work but emit deprecation
warnings. New deployments should use ``AGENT_RELAY_*``.
"""

from __future__ import annotations

import os
import warnings

# Mapping: current env var name → deprecated name
_DEPRECATED: dict[str, str] = {
    "AGENT_RELAY_STATE_DIR": "AGENT_HARNESS_STATE_DIR",
    "AGENT_RELAY_CLIENT_NAME": "AGENT_HARNESS_CLIENT_NAME",
    "AGENT_RELAY_CLIENT_VERSION": "AGENT_HARNESS_CLIENT_VERSION",
    "AGENT_RELAY_SHELL_CWD": "AGENT_HARNESS_SHELL_CWD",
    "AGENT_RELAY_PROVIDER_HOME": "AGENT_HARNESS_PROVIDER_HOME",
    "AGENT_RELAY_USER_HOME": "AGENT_HARNESS_USER_HOME",
    "AGENT_RELAY_DEFAULT_CWD": "AGENT_HARNESS_DEFAULT_CWD",
    "AGENT_RELAY_CUA_DRIVER_BIN": "AGENT_HARNESS_CUA_DRIVER_BIN",
    "AGENT_RELAY_MISE_CONFIG": "AGENT_HARNESS_MISE_CONFIG",
}

_WARNED: set[str] = set()


def getenv(key: str, default: str | None = None) -> str | None:
    """Resolve *key*, falling back to its deprecated name with a warning.

    New name (``AGENT_RELAY_*``) takes precedence. If only the old name
    (``AGENT_HARNESS_*``) is set, a ``FutureWarning`` is emitted once
    per process.
    """
    value = os.environ.get(key)
    if value is not None:
        return value

    deprecated = _DEPRECATED.get(key)
    if deprecated is None:
        return os.environ.get(key, default)

    value = os.environ.get(deprecated)
    if value is not None:
        if key not in _WARNED:
            _WARNED.add(key)
            warnings.warn(
                f"Environment variable {deprecated} is deprecated. Use {key} instead.",
                FutureWarning,
                stacklevel=2,
            )
        return value

    return default
