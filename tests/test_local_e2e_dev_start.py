"""Local-only e2e smokes for the real MCP dev tool surface."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

pytestmark = pytest.mark.skipif(
    os.environ.get("AGENT_HARNESS_RUN_LOCAL_E2E") != "1",
    reason="set AGENT_HARNESS_RUN_LOCAL_E2E=1 to run real provider e2e smokes",
)

PACKAGE_DIR = Path(__file__).resolve().parents[1]
PROFILES = ("deepseek", "qwen", "opencode")


def _tool_data(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if structured:
        return dict(structured)
    return json.loads(result.content[0].text)


def _prompt(sentinel: str) -> str:
    return f"Create no files. Reply exactly {sentinel} and nothing else. Then exit."


def _args(profile: str, transport: str, sentinel: str, cwd: Path) -> dict[str, Any]:
    args: dict[str, Any] = {
        "profile": profile,
        "transport": transport,
        "autonomy": "edit_local",
        "external_context": "allowed",
        "sensitivity": "normal",
        "prompt": _prompt(sentinel),
        "cwd": str(cwd),
    }
    if profile == "deepseek":
        args["model"] = "deepseek-v4-flash"
    if profile == "opencode":
        args["model"] = "glm-5.2"
    return args


def _mcporter_config(tmp_path: Path) -> Path:
    uv = shutil.which("uv")
    if not uv:
        pytest.skip("uv is required for local MCP e2e smokes")
    state_root = tmp_path / "mcporter-state"
    state_root.mkdir()
    config_path = tmp_path / "mcporter.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "agents": {
                        "type": "stdio",
                        "command": uv,
                        "args": ["run", "--directory", str(PACKAGE_DIR), "agents-mcp"],
                        "env": {
                            "AGENT_CROSSBAR_STATE_DIR": str(state_root),
                            "AGENT_CROSSBAR_CLIENT_NAME": "local-e2e",
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return config_path


def _mcporter_call(
    config_path: Path, selector: str, *args: str, timeout_sec: int = 180
) -> dict[str, Any]:
    npx = shutil.which("npx")
    if not npx:
        pytest.skip("npx is required for mcporter local e2e smokes")
    completed = subprocess.run(
        [npx, "mcporter", "--config", str(config_path), "call", selector, *args],
        check=False,
        cwd=PACKAGE_DIR,
        text=True,
        capture_output=True,
        timeout=timeout_sec,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


async def _stdio_call_once(
    state_root: Path,
    tool: str,
    args: dict[str, Any],
    *,
    timeout_sec: int = 180,
) -> dict[str, Any]:
    uv = shutil.which("uv")
    if not uv:
        pytest.skip("uv is required for local MCP e2e smokes")
    env = os.environ.copy()
    env["AGENT_CROSSBAR_STATE_DIR"] = str(state_root)
    env["AGENT_CROSSBAR_CLIENT_NAME"] = "short-lived-stdio-e2e"
    params = StdioServerParameters(
        command=uv,
        args=["run", "--directory", str(PACKAGE_DIR), "agents-mcp"],
        env=env,
        cwd=str(PACKAGE_DIR),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                tool, args, read_timeout_seconds=timedelta(seconds=timeout_sec)
            )
            return _tool_data(result)


def _short_lived_stdio_call(
    state_root: Path,
    tool: str,
    args: dict[str, Any],
    *,
    timeout_sec: int = 180,
) -> dict[str, Any]:
    async def scenario() -> dict[str, Any]:
        return await _stdio_call_once(state_root, tool, args, timeout_sec=timeout_sec)

    return anyio.run(scenario)


def _wait_for_short_lived_stdio_result(
    state_root: Path, job_id: str, sentinel: str
) -> dict[str, Any]:
    deadline = time.monotonic() + 180
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        result = _short_lived_stdio_call(
            state_root, "job_result", {"job_id": job_id}, timeout_sec=60
        )
        last = result
        if result.get("error") == "result_not_ready":
            time.sleep(2)
            continue
        assert result.get("ok") is True, result
        assert sentinel in str(result.get("summary") or result.get("output") or ""), result
        return result
    tail = _short_lived_stdio_call(
        state_root, "job_tail", {"job_id": job_id, "max_bytes": 20000}, timeout_sec=60
    )
    pytest.fail(
        f"short-lived stdio job {job_id} did not complete with {sentinel}; last={last}; tail={tail}"
    )


def _wait_for_mcporter_result(config_path: Path, job_id: str, sentinel: str) -> dict[str, Any]:
    deadline = time.monotonic() + 180
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        result = _mcporter_call(
            config_path, "agents.job_result", f"job_id={job_id}", timeout_sec=60
        )
        last = result
        if result.get("error") == "result_not_ready":
            time.sleep(2)
            continue
        assert result.get("ok") is True, result
        assert sentinel in str(result.get("summary") or result.get("output") or ""), result
        return result
    tail = _mcporter_call(
        config_path, "agents.job_tail", f"job_id={job_id}", "max_bytes=20000", timeout_sec=60
    )
    pytest.fail(f"mcporter job {job_id} did not complete with {sentinel}; last={last}; tail={tail}")


async def _with_session(fn):
    uv = shutil.which("uv")
    if not uv:
        pytest.skip("uv is required for local MCP e2e smokes")
    with tempfile.TemporaryDirectory(prefix="agents-mcp-local-e2e-") as state_root:
        env = os.environ.copy()
        env["AGENT_CROSSBAR_STATE_DIR"] = state_root
        params = StdioServerParameters(
            command=uv,
            args=["run", "--directory", str(PACKAGE_DIR), "agents-mcp"],
            env=env,
            cwd=str(PACKAGE_DIR),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await fn(session, Path(state_root))


async def _wait_for_successful_result(
    session: ClientSession,
    job_id: str,
    sentinel: str,
    *,
    timeout_sec: int = 180,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        result = _tool_data(await session.call_tool("job_result", {"job_id": job_id}))
        last = result
        if result.get("error") == "result_not_ready":
            await anyio.sleep(2)
            continue
        assert result.get("ok") is True, result
        output = str(result.get("summary") or result.get("output") or "")
        assert sentinel in output, result
        return result
    tail = _tool_data(await session.call_tool("job_tail", {"job_id": job_id, "max_bytes": 20000}))
    pytest.fail(f"job {job_id} did not complete with {sentinel}; last={last}; tail={tail}")


def test_local_mcp_dev_sync_print_returns_expected_sentinel(tmp_path):
    async def scenario(session: ClientSession, _state_root: Path):
        for profile in PROFILES:
            sentinel = f"AGENTS_MCP_DEV_E2E_SYNC_PRINT_{profile.upper()}"
            result = _tool_data(
                await session.call_tool(
                    "dev_sync",
                    _args(profile, "print", sentinel, tmp_path),
                    read_timeout_seconds=timedelta(seconds=180),
                )
            )
            assert result.get("ok") is True, result
            assert sentinel in str(result.get("output") or ""), result

    anyio.run(_with_session, scenario)


def test_local_mcp_dev_start_print_completes_with_expected_sentinel(tmp_path):
    async def scenario(session: ClientSession, _state_root: Path):
        for profile in PROFILES:
            sentinel = f"AGENTS_MCP_DEV_E2E_ASYNC_PRINT_{profile.upper()}"
            start = _tool_data(
                await session.call_tool("dev_start", _args(profile, "print", sentinel, tmp_path))
            )
            assert start.get("ok") is True, start
            await _wait_for_successful_result(session, start["job_id"], sentinel)

    anyio.run(_with_session, scenario)


def test_local_mcp_dev_sync_tmux_returns_expected_sentinel(tmp_path):
    async def scenario(session: ClientSession, _state_root: Path):
        for profile in PROFILES:
            sentinel = f"AGENTS_MCP_DEV_E2E_SYNC_TMUX_{profile.upper()}"
            result = _tool_data(
                await session.call_tool(
                    "dev_sync",
                    _args(profile, "tmux", sentinel, tmp_path),
                    read_timeout_seconds=timedelta(seconds=180),
                )
            )
            assert result.get("ok") is True, result
            output = str(result.get("summary") or result.get("output") or "")
            assert sentinel in output, result

    anyio.run(_with_session, scenario)


def test_local_mcp_dev_start_tmux_completes_with_expected_sentinel(tmp_path):
    async def scenario(session: ClientSession, _state_root: Path):
        for profile in PROFILES:
            sentinel = f"AGENTS_MCP_DEV_E2E_ASYNC_TMUX_{profile.upper()}"
            start = _tool_data(
                await session.call_tool("dev_start", _args(profile, "tmux", sentinel, tmp_path))
            )
            assert start.get("ok") is True, start
            await _wait_for_successful_result(session, start["job_id"], sentinel)

    anyio.run(_with_session, scenario)


def test_local_short_lived_stdio_qwen_dev_sync_print_uses_yolo_shell(tmp_path):
    state_root = tmp_path / "short-lived-state"
    state_root.mkdir()
    sentinel = "AGENTS_MCP_SHORT_STDIO_QWEN_PRINT_YOLO"
    result = _short_lived_stdio_call(
        state_root,
        "dev_sync",
        {
            **_args("qwen", "print", sentinel, tmp_path),
            "timeout_sec": 120,
            "prompt": f"Run shell date and print exactly {sentinel} followed by the date output.",
        },
        timeout_sec=180,
    )

    assert result.get("ok") is True, result
    assert result.get("selected_candidate") == "qwen -p -y"
    assert sentinel in str(result.get("output") or ""), result
    stderr = "\n".join(str(attempt.get("stderr") or "") for attempt in result.get("attempts") or [])
    assert "requires user approval" not in stderr


def test_local_short_lived_stdio_qwen_dev_start_tmux_finalizes_result(tmp_path):
    state_root = tmp_path / "short-lived-state"
    state_root.mkdir()
    sentinel = "AGENTS_MCP_SHORT_STDIO_QWEN_TMUX_YOLO"
    start = _short_lived_stdio_call(
        state_root,
        "dev_start",
        {
            **_args("qwen", "tmux", sentinel, tmp_path),
            "prompt": f"Run shell date and print exactly {sentinel} followed by the date output.",
        },
        timeout_sec=60,
    )

    assert start.get("ok") is True, start
    result = _wait_for_short_lived_stdio_result(state_root, start["job_id"], sentinel)
    assert result.get("ok") is True, result


def test_local_short_lived_stdio_reasonix_dev_sync_print_uses_shell(tmp_path):
    state_root = tmp_path / "short-lived-state"
    state_root.mkdir()
    sentinel = "AGENTS_MCP_SHORT_STDIO_REASONIX_PRINT_SHELL"
    result = _short_lived_stdio_call(
        state_root,
        "dev_sync",
        {
            **_args("reasonix", "print", sentinel, tmp_path),
            "model": "deepseek-v4-flash",
            "timeout_sec": 180,
            "prompt": f"Run shell date and print exactly {sentinel} followed by the date output.",
        },
        timeout_sec=220,
    )

    assert result.get("ok") is True, result
    assert str(result.get("selected_candidate") or "").startswith("reasonix run deepseek-v4-flash")
    assert sentinel in str(result.get("output") or ""), result


def test_local_short_lived_stdio_reasonix_dev_start_tmux_uses_shell(tmp_path):
    state_root = tmp_path / "short-lived-state"
    state_root.mkdir()
    sentinel = "AGENTS_MCP_SHORT_STDIO_REASONIX_TMUX_SHELL"
    start = _short_lived_stdio_call(
        state_root,
        "dev_start",
        {
            **_args("reasonix", "tmux", sentinel, tmp_path),
            "model": "deepseek-v4-flash",
            "prompt": f"Run shell date and print exactly {sentinel} followed by the date output.",
        },
        timeout_sec=60,
    )

    assert start.get("ok") is True, start
    result = _wait_for_short_lived_stdio_result(state_root, start["job_id"], sentinel)
    assert result.get("ok") is True, result


def test_local_mcporter_qwen_dev_sync_print_uses_yolo_shell(tmp_path):
    config_path = _mcporter_config(tmp_path)
    sentinel = "AGENTS_MCP_MCPORTER_QWEN_PRINT_YOLO"
    result = _mcporter_call(
        config_path,
        "agents.dev_sync",
        "profile=qwen",
        "transport=print",
        f"cwd={tmp_path}",
        "timeout_sec=120",
        f"prompt=Run shell date and print exactly {sentinel} followed by the date output.",
    )

    assert result.get("ok") is True, result
    assert result.get("selected_candidate") == "qwen -p -y"
    assert sentinel in str(result.get("output") or ""), result
    stderr = "\n".join(str(attempt.get("stderr") or "") for attempt in result.get("attempts") or [])
    assert "requires user approval" not in stderr


def test_local_mcporter_qwen_dev_start_tmux_finalizes_short_lived_call(tmp_path):
    config_path = _mcporter_config(tmp_path)
    sentinel = "AGENTS_MCP_MCPORTER_QWEN_TMUX_YOLO"
    start = _mcporter_call(
        config_path,
        "agents.dev_start",
        "profile=qwen",
        "transport=tmux",
        "autonomy=edit_local",
        "external_context=allowed",
        "sensitivity=normal",
        f"cwd={tmp_path}",
        f"prompt=Run shell date and print exactly {sentinel} followed by the date output.",
    )

    assert start.get("ok") is True, start
    result = _wait_for_mcporter_result(config_path, start["job_id"], sentinel)
    assert result.get("ok") is True, result
