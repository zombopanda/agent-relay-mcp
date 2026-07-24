"""Provider-neutral model-discovery runner with an injectable process boundary.

Every CLI subprocess is argv-only (no shell) and bounded by a timeout.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Protocol

from . import __version__


@dataclass(frozen=True)
class DiscoveryRun:
    returncode: int
    stdout: str
    stderr: str


class DiscoveryProcess(Protocol):
    """Protocol for a bounded, argv-only subprocess that returns stdout."""

    def run(
        self,
        args: list[str],
        *,
        timeout: float | None = None,
        cwd: str | None = None,
    ) -> DiscoveryRun: ...


# ── Codex JSON-Lines session protocol ────────────────────────────────────────


class CodexSession(Protocol):
    """Injectable JSON-Lines session for the Codex App Server protocol.

    ``send`` writes a single JSON line, ``read_line`` returns the next
    complete line (or ``None`` when no data is available / EOF),
    ``terminate`` kills the underlying process.

    Production: :class:`PopenCodexSession`.  Tests: fake session.
    """

    def send(self, line: str) -> None: ...

    def read_line(self, timeout: float | None = None) -> str | None: ...

    def terminate(self) -> None: ...


class PopenCodexSession:
    """Production CodexSession wrapping ``subprocess.Popen`` with a live loop.

    Uses non-blocking reads on stdout with a poll loop so stdin stays
    open for the full protocol exchange.  *args* is passed directly to
    ``subprocess.Popen`` (argv-only, no shell).
    """

    def __init__(self, args: list[str]) -> None:
        self._proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
        )
        self._buffer = bytearray()
        self._closed = False

    def send(self, line: str) -> None:
        if self._closed:
            raise BrokenPipeError("session closed")
        assert self._proc.stdin is not None
        self._proc.stdin.write((line + "\n").encode("utf-8"))
        self._proc.stdin.flush()

    def read_line(self, timeout: float | None = None) -> str | None:
        if self._closed:
            return None
        import select

        assert self._proc.stdout is not None
        deadline = time.monotonic() + (timeout or 30.0)
        while True:
            # Check if leftover bytes from a previous read already form a complete line
            idx = self._buffer.find(b"\n")
            if idx != -1:
                line = self._buffer[:idx].decode("utf-8").strip()
                self._buffer = self._buffer[idx + 1 :]
                return line if line else None

            remaining = max(0.0, deadline - time.monotonic())
            if remaining <= 0:
                return None
            ready, _, _ = select.select([self._proc.stdout], [], [], min(remaining, 1.0))
            if not ready:
                continue
            chunk = self._proc.stdout.read1(4096)
            if not chunk:
                # EOF
                self._closed = True
                if self._buffer:
                    line = self._buffer.decode("utf-8").strip()
                    self._buffer = bytearray()
                    return line if line else None
                return None
            self._buffer.extend(chunk)

    def terminate(self) -> None:
        self._closed = True
        try:
            self._proc.kill()
        except OSError:
            pass
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


# ── Codex JSON-RPC helpers ───────────────────────────────────────────────────


def _make_request(method: str, req_id: int, params: dict[str, Any] | None = None) -> str:
    """Build a JSON-RPC 2.0 request line."""
    msg: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
    }
    if params is not None:
        msg["params"] = params
    return json.dumps(msg)


def _make_notification(method: str, params: dict[str, Any] | None = None) -> str:
    """Build a JSON-RPC 2.0 notification line (no id)."""
    msg: dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": method,
    }
    if params is not None:
        msg["params"] = params
    return json.dumps(msg)


# ── JSON-Lines low-level helpers ─────────────────────────────────────────────


def _read_jsonl_line(buffer: bytearray) -> tuple[str | None, bytearray]:
    """Extract one JSON-Lines message from *buffer*.

    Returns ``(json_str, remaining_buffer)`` or ``(None, buffer)`` if no
    complete line is available yet.
    """
    idx = buffer.find(b"\n")
    if idx == -1:
        return None, buffer
    line = buffer[:idx].decode("utf-8").strip()
    return line, buffer[idx + 1 :]


# ── Model discovery ──────────────────────────────────────────────────────────


def discover_codex_models(
    session: CodexSession,
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Discover Codex models through the Codex App Server JSON-lines protocol.

    Uses a live request/response loop on *session*:

    1. Send ``initialize`` → read response.
    2. Send ``initialized``.
    3. Send ``model/list`` → read response, collecting models.
    4. While ``nextCursor`` is not null, send another ``model/list`` with
       the cursor and read the next page.
    5. Always call ``session.terminate()`` in ``finally``.

    Unrelated notifications (messages without an ``id``) are silently
    skipped.  JSON-RPC errors on ``model/list`` are propagated.  A
    bounded overall *timeout* guards the whole exchange.
    """
    deadline = time.monotonic() + timeout
    all_models: list[dict[str, Any]] = []
    next_request_id = 1

    try:
        # --- initialize ---
        init_req = _make_request(
            "initialize",
            next_request_id,
            {
                "clientInfo": {"name": "agent-crossbar", "version": __version__},
                "capabilities": {},
            },
        )
        init_id = next_request_id
        next_request_id += 1
        session.send(init_req)

        # Wait for initialize response (skip unrelated notifications)
        remaining = max(0.0, deadline - time.monotonic())
        init_response = _read_until_response(session, init_id, remaining)
        if init_response is None:
            return {"ok": False, "error": "codex_initialize_timeout", "models": []}
        if "error" in init_response:
            err = init_response["error"]
            return {
                "ok": False,
                "error": f"codex_initialize_error: {err.get('message', str(err))}",
                "models": [],
            }

        # --- initialized notification ---
        session.send(_make_notification("initialized"))

        # --- model/list loop (paginate until nextCursor is null) ---
        cursor: str | None = None
        while True:
            list_req = _make_request(
                "model/list",
                next_request_id,
                {
                    "limit": 100,
                    "includeHidden": False,
                    **({"cursor": cursor} if cursor else {}),
                },
            )
            list_id = next_request_id
            next_request_id += 1
            session.send(list_req)

            remaining = max(0.0, deadline - time.monotonic())
            list_response = _read_until_response(session, list_id, remaining)
            if list_response is None:
                return {"ok": False, "error": "codex_model_list_timeout", "models": all_models}

            if "error" in list_response:
                err = list_response["error"]
                return {
                    "ok": False,
                    "error": f"codex_model_list_error: {err.get('message', str(err))}",
                    "models": all_models,
                }

            result = list_response.get("result", {})
            if isinstance(result, dict):
                data = result.get("data", [])
                if isinstance(data, list):
                    all_models.extend(data)
                next_cursor = result.get("nextCursor")
                if not next_cursor:
                    break
                cursor = next_cursor
            else:
                break

        return {"ok": True, "models": all_models}

    finally:
        session.terminate()


def _read_until_response(
    session: CodexSession,
    expected_id: int,
    timeout: float,
) -> dict[str, Any] | None:
    """Read JSON-lines from *session* until a response with *expected_id*.

    Returns the parsed message dict, or ``None`` on timeout / EOF.
    Unrelated notifications (no ``id`` field) are silently consumed.
    """
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        line = session.read_line(timeout=remaining)
        if line is None:
            return None
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):
            continue
        # Skip notifications (no id field)
        if "id" not in msg:
            continue
        if msg["id"] == expected_id:
            return msg
        # Response for a different id — still consider it unexpected; skip
        continue


# ── OpenCode model discovery ─────────────────────────────────────────────────


def discover_opencode_models(
    runner: DiscoveryProcess,
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Discover OpenCode models via ``opencode models``.

    Returns a list of model IDs (one per line, each containing ``/``).
    """
    result = runner.run(["opencode", "models"], timeout=timeout)
    if result.returncode != 0:
        return {
            "ok": False,
            "error": f"opencode_models_exit_{result.returncode}",
            "stderr": result.stderr[:500],
            "models": [],
        }
    models = [line.strip() for line in result.stdout.splitlines() if "/" in line and line.strip()]
    return {"ok": True, "models": models}
