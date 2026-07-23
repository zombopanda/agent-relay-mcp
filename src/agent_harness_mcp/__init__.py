"""Compatibility shim for the deprecated ``agent_harness_mcp`` import.

Agent Relay MCP renamed its import package from ``agent_harness_mcp``
to ``agent_relay_mcp`` in v0.1.3.  This module re-exports the public API
so that existing code does not break immediately, but every import emits
a ``FutureWarning``.

**Migration**: replace ``import agent_harness_mcp`` with
``import agent_relay_mcp`` and ``from agent_harness_mcp.X import Y`` with
``from agent_relay_mcp.X import Y``.

This shim will be removed in v0.4.0.
"""

from __future__ import annotations

import sys
import warnings

warnings.warn(
    "The 'agent_harness_mcp' package is deprecated. "
    "Use 'agent_relay_mcp' instead. "
    "This shim will be removed in v0.4.0.",
    FutureWarning,
    stacklevel=2,
)

# Re-export everything that agent_relay_mcp exposes at package level
# Make submodules accessible
from agent_relay_mcp import (  # noqa: E402, I001
    __version__ as __version__,  # noqa: E402, F401
    acp_lifecycle as acp_lifecycle,
    acp_runtime as acp_runtime,
    adapters as adapters,
    agent_runner as agent_runner,
    cli as cli,
    context as context,
    discovery as discovery,
    discovery_runner as discovery_runner,
    env_compat as env_compat,
    envelope as envelope,
    jobs as jobs,
    model_cache as model_cache,
    models as models,
    profiles as profiles,
    providers as providers,
    readiness as readiness,
    redaction as redaction,
    runner as runner,
    server as server,
    shell_server as shell_server,
    telemetry as telemetry,
    tmux_output as tmux_output,
    validation as validation,
)

# Allow `from agent_harness_mcp.X import Y`
# by ensuring submodules are importable
for _mod_name in (
    "acp_lifecycle",
    "acp_runtime",
    "adapters",
    "agent_runner",
    "cli",
    "context",
    "discovery",
    "discovery_runner",
    "envelope",
    "env_compat",
    "jobs",
    "model_cache",
    "models",
    "profiles",
    "providers",
    "readiness",
    "redaction",
    "runner",
    "server",
    "shell_server",
    "telemetry",
    "tmux_output",
    "validation",
):
    _full = f"agent_harness_mcp.{_mod_name}"
    _target = f"agent_relay_mcp.{_mod_name}"
    if _full not in sys.modules:
        sys.modules[_full] = __import__(_target, fromlist=[_mod_name])
