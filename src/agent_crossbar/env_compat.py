"""Backward-compatible environment variable resolution.

Agent Crossbar (v0.2.0) renamed from the internal ``agent-harness-mcp``.
The old ``AGENT_HARNESS_*`` env var names still work but emit deprecation
warnings. New deployments should use ``AGENT_CROSSBAR_*``.
"""

from __future__ import annotations

import os
import warnings

# Mapping: current env var name → deprecated name
_DEPRECATED: dict[str, str] = {
    "AGENT_CROSSBAR_STATE_DIR": "AGENT_HARNESS_STATE_DIR",
    "AGENT_CROSSBAR_CLIENT_NAME": "AGENT_HARNESS_CLIENT_NAME",
    "AGENT_CROSSBAR_CLIENT_VERSION": "AGENT_HARNESS_CLIENT_VERSION",
    "AGENT_CROSSBAR_SHELL_CWD": "AGENT_HARNESS_SHELL_CWD",
    "AGENT_CROSSBAR_PROVIDER_HOME": "AGENT_HARNESS_PROVIDER_HOME",
    "AGENT_CROSSBAR_USER_HOME": "AGENT_HARNESS_USER_HOME",
    "AGENT_CROSSBAR_DEFAULT_CWD": "AGENT_HARNESS_DEFAULT_CWD",
    "AGENT_CROSSBAR_CUA_DRIVER_BIN": "AGENT_HARNESS_CUA_DRIVER_BIN",
    "AGENT_CROSSBAR_MISE_CONFIG": "AGENT_HARNESS_MISE_CONFIG",
}

_WARNED: set[str] = set()


def getenv(key: str, default: str | None = None) -> str | None:
    """Resolve *key*, falling back to its deprecated name with a warning.

    New name (``AGENT_CROSSBAR_*``) takes precedence. If only the old name
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
