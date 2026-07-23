"""Stub tests for the npm launcher (bin/agent-crossbar.mjs)."""

import subprocess
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parent.parent / "bin" / "agent-crossbar.mjs"


def test_launcher_syntax():
    """The launcher must be valid JavaScript."""
    result = subprocess.run(
        ["node", "--check", str(LAUNCHER)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_launcher_argv_passthrough():
    """The launcher must pass arguments through to uvx."""
    launcher = LAUNCHER.read_text()
    # The launcher slices process.argv at index 2
    assert "process.argv.slice(2)" in launcher
    # It constructs: uvx agent-crossbar <args>
    assert "agent-crossbar" in launcher
    # It has uvx as primary spawn target
    assert '"uvx"' in launcher


def test_launcher_error_exit():
    """When uvx is not found, the launcher must exit(1), not throw."""
    launcher = LAUNCHER.read_text()
    # The error handler uses process.exit(1)
    assert "process.exit(1)" in launcher
    # It prints a helpful message about uv requirement
    assert "uv" in launcher.lower()


def test_launcher_signal_forwarding():
    """The launcher must forward signals to the child process."""
    launcher = LAUNCHER.read_text()
    # On exit with signal, the launcher kills itself with the same signal
    assert "process.kill(process.pid, signal)" in launcher
