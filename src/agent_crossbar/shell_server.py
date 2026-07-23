"""YOLO shell MCP used by external dev providers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from agent_crossbar.env_compat import getenv

mcp = FastMCP("agent_crossbar_shell")


def _cwd() -> Path:
    raw = getenv("AGENT_CROSSBAR_SHELL_CWD") or os.getcwd()
    return Path(raw).expanduser().resolve()


@mcp.tool()
def run_shell_command(command: str, timeout_sec: int = 60) -> dict[str, Any]:
    """Run a shell command in the configured working directory."""
    cwd = _cwd()
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "error": "timed_out",
            "message": str(exc),
            "cwd": str(cwd),
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }
    except OSError as exc:
        return {
            "ok": False,
            "error": exc.__class__.__name__,
            "message": str(exc),
            "cwd": str(cwd),
            "stdout": "",
            "stderr": "",
        }

    return {
        "ok": result.returncode == 0,
        "exit_code": result.returncode,
        "cwd": str(cwd),
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
