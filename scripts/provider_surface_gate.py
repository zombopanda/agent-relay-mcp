"""Live provider surface gate for before-push checks.

This script intentionally calls real MCP tools and real providers. Use it for
provider/harness behavior changes, not as part of the default unit test suite.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

PACKAGE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MAX_RUNTIME_SEC = 1800
RESULT_COMPLETION_GRACE_SEC = 15
BLOCKING_PROMPTS = (
    "Allow once",
    "Allow always",
    "Reject",
)
_REASONIX_FOOTER_RE = re.compile(
    r"— turns:\d+ cache:\d+(?:\.\d+)?% cost:\$\d+(?:\.\d+)? "
    r"save-vs-claude:\d+(?:\.\d+)?%"
)


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    message: str


@dataclass(frozen=True)
class GateCase:
    profile: str
    model: str
    effort: str | None
    task: str
    interactive: bool
    max_runtime_sec: int = DEFAULT_MAX_RUNTIME_SEC

    @property
    def label(self) -> str:
        effort = self.effort or "default"
        interactive = "interactive" if self.interactive else "oneshot"
        return f"{self.profile}/{self.model}/{effort}/{self.task}/{interactive}"


def _contains_blocking_prompt(output: str) -> bool:
    return any(prompt in output for prompt in BLOCKING_PROMPTS)


def _tool_data(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if structured:
        return dict(structured)
    return json.loads(result.content[0].text)


def _dev_prompt() -> str:
    return (
        "Create exactly two files in the current working directory: "
        "reverse_words.py and test_reverse_words.py. "
        "reverse_words.py must define reverse_words(text: str) -> str, reversing "
        "the letters in each word while preserving word order. "
        "test_reverse_words.py must contain pytest tests for normal words, "
        "multiple spaces, punctuation attached to words, empty string, and unicode. "
        "Run pytest test_reverse_words.py. Finish by reporting the test command "
        "and whether it passed."
    )


def _agent_start_args(case: GateCase, cwd: str | None = None) -> dict[str, Any]:
    """Build agent_start args from a GateCase using the current public API."""
    args: dict[str, Any] = {
        "profile": case.profile,
        "task": case.task,
        "interactive": case.interactive,
        "max_runtime_sec": case.max_runtime_sec,
        "model": case.model,
    }

    if case.task == "dev":
        args["prompt"] = _dev_prompt()
        if cwd is not None:
            args["cwd"] = cwd
    else:
        # ask or review — both use sentinel prompt
        args["prompt"] = "Reply with exactly GPT_PRO_PROVIDER_GATE_OK"

    if case.effort:
        args["effort"] = case.effort
    return args


def _prepare_workspace(cwd: Path) -> CheckResult:
    git = shutil.which("git")
    if git is None:
        return CheckResult(False, "git is not available on PATH")
    completed = subprocess.run(
        [git, "rev-parse", "--is-inside-work-tree"],
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if completed.returncode != 0 or completed.stdout.strip() != "true":
        output = (completed.stdout + completed.stderr)[-4000:]
        return CheckResult(False, f"workspace is not inside a git repo:\n{output}")
    (cwd / "AGENTS.md").write_text(
        "# Disposable provider gate\n\n"
        "This directory is a disposable provider surface gate. "
        "Do not create beads or OpenSpec artifacts. "
        "Do not inspect or modify parent directories. "
        "Implement only the files requested by the prompt and run only the requested test.\n",
        encoding="utf-8",
    )
    return CheckResult(True, "workspace is inside the trusted package repo")


def _workspace_tempdir() -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix=".agents-provider-gate-work-", dir=PACKAGE_DIR)


def _verify_reverse_words_workspace(cwd: Path) -> CheckResult:
    code_path = cwd / "reverse_words.py"
    test_path = cwd / "test_reverse_words.py"
    if not code_path.exists():
        return CheckResult(False, f"missing {code_path.name}")
    if not test_path.exists():
        return CheckResult(False, f"missing {test_path.name}")

    completed = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_path.name)],
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
        timeout=120,
    )
    if completed.returncode != 0:
        output = (completed.stdout + completed.stderr)[-4000:]
        return CheckResult(
            False, f"generated tests failed with exit {completed.returncode}:\n{output}"
        )
    return CheckResult(True, "generated tests passed")


async def _call(
    session: ClientSession, tool: str, args: dict[str, Any], timeout_sec: int = 120
) -> dict[str, Any]:
    result = await session.call_tool(
        tool, args, read_timeout_seconds=timedelta(seconds=timeout_sec)
    )
    return _tool_data(result)


async def _wait_for_result(
    session: ClientSession,
    job_id: str,
    *,
    timeout_sec: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, Any] = {}
    tail: dict[str, Any] = {}
    while time.monotonic() < deadline:
        tail = await _call(
            session, "job_tail", {"job_id": job_id, "max_bytes": 20000}, timeout_sec=60
        )
        tail_text = json.dumps(tail, ensure_ascii=False)
        if _contains_blocking_prompt(tail_text):
            return {"ok": False, "error": "blocking_prompt", "summary": tail_text[-4000:]}, tail

        result = await _call(session, "job_result", {"job_id": job_id}, timeout_sec=60)
        last = result
        if result.get("error") == "result_not_ready":
            await anyio.sleep(2)
            continue
        return result, tail
    return {"ok": False, "error": "timed_out", "summary": str(last)}, tail


def _reasonix_sentinel_with_footer(output: str, *, profile: str) -> bool:
    if profile.casefold() not in {"reasonix", "deepseek"}:
        return False
    lines = [line.strip() for line in output.strip().splitlines() if line.strip()]
    return (
        len(lines) == 2
        and lines[0] == "GPT_PRO_PROVIDER_GATE_OK"
        and _REASONIX_FOOTER_RE.fullmatch(lines[1]) is not None
    )


def _standalone_sentinel_received(sentinel: str, output: str) -> bool:
    """Check whether *sentinel* appears as a standalone line anywhere in output."""
    for line in output.splitlines():
        if line.strip() == sentinel:
            return True
    return False


def _sentinel_after_echo(sentinel: str, output: str) -> bool:
    """Accept *sentinel* when it appears after the echoed prompt line.

    For pipe-captured tmux output, the first occurrence of the sentinel is
    always the echoed prompt text (e.g. ``Reply with exactly SENTINEL▌``).
    A second, standalone occurrence indicates the assistant actually replied.
    """
    # Find all positions of the sentinel
    positions: list[int] = []
    start = 0
    while True:
        idx = output.find(sentinel, start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + len(sentinel)
    if len(positions) < 2:
        # Single occurrence: accept if it's NOT an echoed prompt
        if positions:
            line_before = output[max(0, positions[0] - 60) : positions[0]]
            if "Reply with exactly" in line_before:
                return False
        return len(positions) == 1 and "Reply with exactly" not in output[: positions[0] + 60]
    # Two or more occurrences: accept (the first is likely the echo)
    return True


def _claude_sentinel_received(sentinel: str, output: str) -> bool:
    """Check whether *sentinel* appears as a distinct assistant answer.

    Claude's native TUI echoes the prompt, so a naive substring match
    would false-positive on the echoed instruction.  This checker:

    1. Accepts any line whose stripped content is exactly *sentinel*.
    2. Accepts a ``⏺``-prefixed line whose content after removing the
       ``⏺`` marker is exactly *sentinel* (case-insensitive).
    3. Rejects everything else — no buried-in-prose substring matches.
    """
    lines = output.splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Standalone sentinel on its own line.
        if stripped == sentinel:
            return True
        # ⏺-prefixed line where the remainder is exactly the sentinel.
        if stripped.startswith("⏺"):
            remainder = stripped[1:].strip()
            if remainder.lower() == sentinel.lower():
                return True
    return False


async def _run_dev_case(session: ClientSession, case: GateCase, cwd: Path) -> CheckResult:
    """Run a dev task via agent_start, poll for completion, verify output."""
    args = _agent_start_args(case, cwd=str(cwd))

    start = await _call(session, "agent_start", args, timeout_sec=120)
    if not start.get("ok"):
        return CheckResult(False, f"{case.label} agent_start failed: {start}")

    job_id = str(start["job_id"])
    result, tail = await _wait_for_result(
        session,
        job_id,
        timeout_sec=case.max_runtime_sec + RESULT_COMPLETION_GRACE_SEC,
    )
    tail_text = json.dumps(tail, ensure_ascii=False)

    if _contains_blocking_prompt(tail_text):
        return CheckResult(False, f"{case.label} blocked on provider prompt:\n{tail_text[-4000:]}")
    if not result.get("ok"):
        summary = str(result.get("summary") or result.get("output") or "")[-4000:]
        return CheckResult(
            False, f"{case.label} failed: {result.get('error', 'unknown')}\n{summary}"
        )

    workspace = _verify_reverse_words_workspace(cwd)
    if not workspace.ok:
        summary = str(result.get("summary") or "")[-4000:]
        return CheckResult(
            False,
            f"{case.label} workspace verification failed: {workspace.message}\nProvider summary:\n{summary}",
        )
    return CheckResult(True, f"{case.label}: {workspace.message}")


async def _run_ask_case(session: ClientSession, case: GateCase) -> CheckResult:
    """Run an ask task via agent_start, poll for completion, check sentinel."""
    if case.interactive:
        return await _run_interactive_ask_case(session, case)
    return await _run_oneshot_ask_case(session, case)


async def _run_oneshot_ask_case(session: ClientSession, case: GateCase) -> CheckResult:
    """Non-interactive ask: agent_start, wait for terminal job_result, check sentinel."""
    args = _agent_start_args(case)
    start = await _call(session, "agent_start", args, timeout_sec=120)
    if not start.get("ok"):
        return CheckResult(False, f"{case.label} agent_start failed: {start}")
    job_id = str(start["job_id"])
    result, _tail = await _wait_for_result(
        session,
        job_id,
        timeout_sec=case.max_runtime_sec + RESULT_COMPLETION_GRACE_SEC,
    )
    if not result.get("ok"):
        return CheckResult(False, f"{case.label} failed: {result}")
    output = result.get("output") or result.get("summary") or ""
    return _check_sentinel(case, output)


async def _run_interactive_ask_case(session: ClientSession, case: GateCase) -> CheckResult:
    """Interactive ask: start job, verify initial response, send second sentinel,
    verify second response, then stop and verify cleanup."""
    args = _agent_start_args(case)
    start = await _call(session, "agent_start", args, timeout_sec=120)
    if not start.get("ok"):
        return CheckResult(False, f"{case.label} agent_start failed: {start}")
    job_id = str(start["job_id"])

    # 1. Wait for initial output (settling) and check first sentinel
    initial, _ = await _poll_tail_text(session, job_id, timeout_sec=60, settling_sec=8.0)
    initial_ok = _check_sentinel(case, initial)
    if not initial_ok.ok:
        await _call(
            session, "job_stop", {"job_id": job_id, "reason": "sentinel_missing"}, timeout_sec=30
        )
        return initial_ok

    # 2. Send a distinct second sentinel via job_send
    second_sentinel = "GPT_PROVIDER_SECOND_SENTINEL_OK"
    send = await _call(
        session,
        "job_send",
        {"job_id": job_id, "text": f"Reply with exactly {second_sentinel}"},
        timeout_sec=60,
    )
    if not send.get("ok"):
        await _call(
            session, "job_stop", {"job_id": job_id, "reason": "send_failed"}, timeout_sec=30
        )
        return CheckResult(False, f"{case.label} job_send failed: {send}")

    # 3. Poll for second sentinel (full output_tail, cleaned, standalone)
    found, _ = await _poll_until_sentinel(session, job_id, second_sentinel, timeout_sec=120)

    # 4. Clean up
    stop = await _call(
        session, "job_stop", {"job_id": job_id, "reason": "gate_complete"}, timeout_sec=30
    )
    cleanup_ok = stop.get("ok", False)
    cleanup_msg = "cleanup ok" if cleanup_ok else "cleanup failed"

    if not found:
        return CheckResult(False, f"{case.label} second sentinel not received ({cleanup_msg})")

    # 5. Verify job reached terminal state after stop
    final = await _call(session, "job_result", {"job_id": job_id}, timeout_sec=30)
    terminal_ok = final.get("ok", False)
    if not terminal_ok:
        return CheckResult(
            False, f"{case.label} job not terminal after stop: {final.get('error', 'unknown')}"
        )

    return CheckResult(True, f"{case.label}: two sentinels, {cleanup_msg}, job terminal")


def _check_sentinel(case: GateCase, output: str) -> CheckResult:
    """Check whether *output* contains the expected gate sentinel."""
    if not isinstance(output, str) or not output.strip():
        return CheckResult(False, f"{case.label} returned no output for sentinel check")
    # Strip ANSI for tmux/interactive output
    if case.interactive:
        output = _clean_ansi(output)
    claude_profile = case.profile.casefold() in {"claude", "opus", "fable"}
    reasonix_profile = case.profile.casefold() in {"reasonix", "deepseek"}
    if reasonix_profile:
        if case.interactive:
            # tmux TUI pipes the echoed prompt — look for second occurrence
            sentinel_received = _sentinel_after_echo("GPT_PRO_PROVIDER_GATE_OK", output)
        else:
            sentinel_received = _reasonix_sentinel_with_footer(output, profile=case.profile)
    elif claude_profile:
        sentinel_received = _claude_sentinel_received("GPT_PRO_PROVIDER_GATE_OK", output)
    else:
        sentinel_received = output.strip() == "GPT_PRO_PROVIDER_GATE_OK"
    if sentinel_received:
        return CheckResult(True, f"{case.label}: live sentinel received")
    return CheckResult(False, f"{case.label} returned no exact string gate sentinel: {output!r}")


def _clean_ansi(text: str) -> str:
    """Strip ANSI escape sequences from tmux TUI output for sentinel matching."""
    from agent_crossbar.tmux_output import normalize_tmux_output

    return normalize_tmux_output(text)


def _tail_text(tail: dict[str, Any]) -> str:
    """Extract visible text from a job_tail response (handles both dict and string)."""
    ot = tail.get("output_tail")
    return ot.get("text", "") if isinstance(ot, dict) else (ot or "")


async def _poll_tail_text(
    session: ClientSession,
    job_id: str,
    *,
    timeout_sec: int,
    settling_sec: float,
    since_bytes: int | None = None,
) -> tuple[str, int]:
    """Poll job_tail until accumulated visible output stabilises.

    Returns (text, next_bytes) suitable for a subsequent incremental poll.
    """
    deadline = time.monotonic() + timeout_sec
    last_text = ""
    last_bytes = 0
    stable_since = time.monotonic()
    args: dict[str, Any] = {"job_id": job_id, "max_bytes": 50000}
    if since_bytes is not None:
        args["output_since_bytes"] = since_bytes
    while time.monotonic() < deadline:
        tail = await _call(session, "job_tail", args, timeout_sec=60)
        current = _tail_text(tail)
        ot = tail.get("output_tail")
        next_bytes = ot.get("bytes", 0) if isinstance(ot, dict) else last_bytes
        if current and current == last_text:
            if time.monotonic() - stable_since >= settling_sec:
                return current, next_bytes
        else:
            last_text = current
            last_bytes = next_bytes
            stable_since = time.monotonic()
        args.pop("output_since_bytes", None)  # full poll after first incremental
        await anyio.sleep(1)
    return last_text, last_bytes


async def _poll_until_sentinel(
    session: ClientSession,
    job_id: str,
    sentinel: str,
    *,
    timeout_sec: int,
) -> tuple[bool, str]:
    """Poll job_tail with full output_tail until *sentinel* appears as a
    standalone line in cleaned output.  Returns (found, cleaned_text)."""
    deadline = time.monotonic() + timeout_sec
    last_text = ""
    while time.monotonic() < deadline:
        tail = await _call(
            session, "job_tail", {"job_id": job_id, "max_bytes": 100000}, timeout_sec=60
        )
        current = _tail_text(tail)
        if current and current != last_text:
            last_text = current
            clean = _clean_ansi(current)
            if _sentinel_after_echo(sentinel, clean):
                return True, clean
        await anyio.sleep(1)
    return False, _clean_ansi(last_text)


def _server_params(env: dict[str, str]) -> StdioServerParameters:
    """Return StdioServerParameters for the installed ``agents-mcp`` entrypoint.

    Resolves the console script alongside the current Python interpreter
    (both live in the same venv ``bin/`` directory).  This exercises the
    real user-visible entrypoint — not ``python -m`` on a module without
    a ``__main__`` block.
    """
    bin_dir = Path(sys.executable).parent
    return StdioServerParameters(
        command=str(bin_dir / "agents-mcp"),
        args=[],
        env=env,
    )


async def _run_cases(cases: list[GateCase]) -> int:
    with tempfile.TemporaryDirectory(prefix="agents-provider-gate-state-") as state_root:
        env = os.environ.copy()
        env["AGENT_CROSSBAR_STATE_DIR"] = state_root
        env["AGENT_CROSSBAR_CLIENT_NAME"] = "provider-surface-gate"

        params = _server_params(env)
        failed = False
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for case in cases:
                    if case.task == "dev":
                        with _workspace_tempdir() as work_dir:
                            cwd = Path(work_dir)
                            prepared = _prepare_workspace(cwd)
                            if not prepared.ok:
                                print(
                                    f"{case.label} workspace preparation failed: {prepared.message}"
                                )
                                failed = True
                                continue
                            result = await _run_dev_case(session, case, cwd)
                    else:
                        result = await _run_ask_case(session, case)
                    print(result.message)
                    if not result.ok:
                        failed = True
        return 1 if failed else 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    # Strip exactly one leading '--' separator that npm/pnpm passes through
    if argv and argv[0] == "--":
        argv = argv[1:]
    parser = argparse.ArgumentParser(description="Run live provider surface gate")
    parser.add_argument("--profile", action="append", required=True)
    parser.add_argument("--model", action="append", required=True)
    parser.add_argument("--effort", action="append", default=[])
    parser.add_argument("--task", action="append", choices=["ask", "review", "dev"])
    parser.add_argument(
        "--interactive", type=lambda s: s.lower() in ("true", "1", "yes"), default=False
    )
    parser.add_argument("--max-runtime-sec", type=int, default=DEFAULT_MAX_RUNTIME_SEC)
    return parser.parse_args(argv)


def _cases_from_args(args: argparse.Namespace) -> list[GateCase]:
    models = args.model
    efforts = args.effort or [None]
    tasks = args.task or ["dev"]
    return [
        GateCase(
            profile=profile,
            model=model,
            effort=effort,
            task=task,
            interactive=args.interactive,
            max_runtime_sec=args.max_runtime_sec,
        )
        for profile in args.profile
        for model in models
        for effort in efforts
        for task in tasks
    ]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    valid_tasks = {"ask", "review", "dev"}
    unsupported = [task for task in (args.task or ["dev"]) if task not in valid_tasks]
    if unsupported:
        print(
            f"provider_surface_gate supports only task in {valid_tasks}: {unsupported}",
            file=sys.stderr,
        )
        return 2
    return anyio.run(_run_cases, _cases_from_args(args))


if __name__ == "__main__":
    raise SystemExit(main())
