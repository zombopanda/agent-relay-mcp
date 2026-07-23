"""Helpers for interpreting provider TUI output captured from tmux panes."""

from __future__ import annotations

import re

_ANSI_RE = re.compile(r"\x1b(?:\][^\a]*(?:\a|\x1b\\)|\[[0-?]*[ -/]*[@-~]|[@-Z\\-_])")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_REASONIX_REPLY_RE = re.compile(r"‹\s*reply", re.IGNORECASE)
_REASONIX_READY_RE = re.compile(
    r"(?:ask\s*anything|type\s*a\s*message\s*to\s*start\s*your\s*session)",
    re.IGNORECASE,
)
_SESSION_RESUMED_RE = re.compile(r"resumed\s*session", re.IGNORECASE)
_CLAUDE_STYLE_ANSWER_RE = re.compile(
    r"(?m)^\s*⏺\s*(?!(?:Bash|Read|Write|Edit|Glob|Grep|Task|WebFetch|WebSearch|Tool|Skill)\b)\S"
)
_CLAUDE_IDLE_NOTIFICATION_RE = re.compile(
    r"\x1b\]777;notify;Claude Code;Claude is waiting for your input(?:\x07|\x1b\\)",
    re.IGNORECASE,
)
_CLAUDE_IDLE_FOOTER_RE = re.compile(
    r"(?m)^\s*⏵⏵\s+(?:bypass permissions|plan mode)\s+on\b",
    re.IGNORECASE,
)
_CLAUDE_BUSY_RE = re.compile(
    r"(?:esc\s*to\s*interrupt|^\s*[✶✽✻]\s+[^\n]*…)",
    re.IGNORECASE | re.MULTILINE,
)
_CLAUDE_FINISHED_RE = re.compile(
    r"(?m)^\s*✻\s*[^\n…]{1,48}?\s+for\s*\d+\s*[smh]?\b",
    re.IGNORECASE,
)
_CLAUDE_PLAN_READY_RE = re.compile(
    r"(?ms)^Claude\s*has\s*written\s*up\s*a\s*plan\s*and\s*is\s*ready\s*to\s*"
    r"execute\.?\s*Would\s*you\s*like\s*to\s*proceed\?\s*❯?\s*1\.\s*Yes,",
    re.IGNORECASE,
)
_CODEX_ANSWER_RE = re.compile(
    r"(?m)^\s*•\s+(?!(?:SessionStart|UserPromptSubmit|PreToolUse|PostToolUse|PermissionRequest|Stop|Working|Running|Ran|Called|Read|Edited|Updated|Explored|Searched|Listed|Wrote|Patched)\b)\S"
)
_CODEX_BUSY_RE = re.compile(r"\besc\s+to\s+interrupt\b", re.IGNORECASE)
_CODEX_STOP_RE = re.compile(r"\bStop\s+hook\b", re.IGNORECASE)
_CODEX_WORKED_FOR_RE = re.compile(r"\bWorked\s+for\s+\d", re.IGNORECASE)
_OPENCODE_PROMPT_RE = re.compile(r"(?m)^\s*›\s+.+$")
_OPENCODE_BUSY_RE = re.compile(r"\besc\s+interrupt\b", re.IGNORECASE)


def normalize_tmux_output(output: str) -> str:
    """Strip terminal control sequences while keeping user-visible text."""
    text = output.replace("\r", "\n")
    previous = None
    while previous != text:
        previous = text
        text = _ANSI_RE.sub("", text)
    return _CONTROL_RE.sub("", text)


def interactive_tmux_output_complete(
    output: str,
    *,
    baseline_bytes: int = 0,
    profile: str | None = None,
) -> bool:
    if len(output.encode("utf-8", errors="replace")) <= baseline_bytes:
        return False

    text = normalize_tmux_output(output)
    if interactive_tmux_session_resumed(output, profile=profile):
        return False

    profile = (profile or "").casefold()
    if profile in {"reasonix", "deepseek"}:
        return _reasonix_output_complete(text)
    if profile in {"claude", "opus"}:
        return _claude_style_output_complete(
            text,
            idle_notified=_claude_latest_turn_idle_notified(output),
        )
    if profile == "codex":
        return _codex_output_complete(text)
    if profile == "opencode":
        return _opencode_output_complete(text)
    if profile:
        return False

    return (
        _reasonix_output_complete(text)
        or _claude_style_output_complete(text)
        or _codex_output_complete(text)
        or _opencode_output_complete(text)
    )


def interactive_tmux_output_summary(
    output: str,
    *,
    profile: str | None = None,
    max_chars: int = 4000,
) -> str:
    text = normalize_tmux_output(output)
    if not text:
        return "Interactive tmux output completed"
    index = _completion_marker_index(text, profile=profile)
    if index >= 0:
        start = max(0, index - max_chars // 3)
        end = min(len(text), index + max_chars)
        return text[start:end][-max_chars:]
    return text[-max_chars:]


def interactive_tmux_session_resumed(output: str, *, profile: str | None = None) -> bool:
    profile = (profile or "").casefold()
    if profile and profile not in {"reasonix", "deepseek"}:
        return False
    return _SESSION_RESUMED_RE.search(normalize_tmux_output(output)) is not None


def _reasonix_output_complete(text: str) -> bool:
    reply = list(_REASONIX_REPLY_RE.finditer(text))
    if not reply:
        return False
    last_reply = reply[-1].start()
    return any(match.start() > last_reply for match in _REASONIX_READY_RE.finditer(text))


def _claude_style_output_complete(text: str, *, idle_notified: bool = False) -> bool:
    if _CLAUDE_PLAN_READY_RE.search(text):
        return True
    answer = list(_CLAUDE_STYLE_ANSWER_RE.finditer(text))
    if not answer:
        return False
    last_answer = answer[-1].start()
    answer_tail = text[last_answer:]
    finished = list(_CLAUDE_FINISHED_RE.finditer(answer_tail))
    busy = list(_CLAUDE_BUSY_RE.finditer(answer_tail))
    if finished and (not busy or finished[-1].start() > busy[-1].start()):
        return True
    if text.rfind("❯") <= last_answer:
        return False
    if idle_notified:
        return True
    return bool(_CLAUDE_IDLE_FOOTER_RE.search(answer_tail)) and not busy


def _claude_latest_turn_idle_notified(output: str) -> bool:
    notifications = list(_CLAUDE_IDLE_NOTIFICATION_RE.finditer(output))
    if not notifications:
        return False
    notification = notifications[-1].start()
    return notification > output.rfind("⏺")


def _codex_output_complete(text: str) -> bool:
    submit = text.rfind("UserPromptSubmit hook")
    search_from = submit if submit >= 0 else text.rfind("\n› ")
    haystack = text[search_from:] if search_from >= 0 else text
    answers = list(_CODEX_ANSWER_RE.finditer(haystack))
    if not answers:
        return False
    answer_tail = haystack[answers[-1].start() :]
    boundary = _CODEX_STOP_RE.search(answer_tail) or _CODEX_WORKED_FOR_RE.search(answer_tail)
    if boundary is None:
        return False
    return _CODEX_BUSY_RE.search(answer_tail[boundary.end() :]) is None


def _opencode_output_complete(text: str) -> bool:
    return _opencode_answer_index(text) >= 0


def _opencode_answer_index(text: str) -> int:
    prompts = list(_OPENCODE_PROMPT_RE.finditer(text))
    if not prompts:
        return -1
    tail_start = prompts[-1].end()
    tail = text[tail_start:]
    if _OPENCODE_BUSY_RE.search(tail):
        return -1

    offset = tail_start
    in_thinking = False
    for line in tail.splitlines(keepends=True):
        stripped = line.strip()
        if not stripped:
            in_thinking = False
            offset += len(line)
            continue
        if stripped.lower().startswith("thinking:"):
            in_thinking = True
            offset += len(line)
            continue
        if in_thinking:
            offset += len(line)
            continue
        if _opencode_status_line(stripped):
            offset += len(line)
            continue
        return offset + len(line) - len(line.lstrip())
    return -1


def _opencode_status_line(line: str) -> bool:
    return (
        line.startswith("▣ Build")
        or line.startswith("BUILD")
        or line.startswith("█")
        or line.startswith("▀")
    )


def _completion_marker_index(text: str, *, profile: str | None = None) -> int:
    profile = (profile or "").casefold()
    if profile in {"reasonix", "deepseek"}:
        matches = list(_REASONIX_REPLY_RE.finditer(text))
        return matches[-1].start() if matches else -1
    if profile in {"claude", "opus"}:
        plan_ready = list(_CLAUDE_PLAN_READY_RE.finditer(text))
        if plan_ready:
            return plan_ready[-1].start()
        matches = list(_CLAUDE_STYLE_ANSWER_RE.finditer(text))
        return matches[-1].start() if matches else -1
    if profile == "codex":
        matches = list(_CODEX_ANSWER_RE.finditer(text))
        return matches[-1].start() if matches else -1
    if profile == "opencode":
        return _opencode_answer_index(text)
    if profile:
        return -1

    matches: list[int] = []
    if match := _REASONIX_REPLY_RE.search(text):
        matches.append(match.start())
    for regex in (_CLAUDE_STYLE_ANSWER_RE, _CODEX_ANSWER_RE):
        found = list(regex.finditer(text))
        if found:
            matches.append(found[-1].start())
    opencode_index = _opencode_answer_index(text)
    if opencode_index >= 0:
        matches.append(opencode_index)
    return max(matches) if matches else -1
