"""Request/result/profile dataclasses and enums for the agent harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Operation(str, Enum):
    REVIEW = "review"
    ADVICE = "advice"
    TEXT = "text"
    DEV = "dev"


class Transport(str, Enum):
    AUTO = "auto"
    PRINT = "print"
    TMUX = "tmux"
    GUI = "gui"


class Autonomy(str, Enum):
    READ_ONLY = "read_only"
    PROPOSE_PATCH = "propose_patch"
    EDIT_LOCAL = "edit_local"


class Sensitivity(str, Enum):
    NORMAL = "normal"
    PRIVATE = "private"
    SECRET = "secret"


# Canonical profiles
CANONICAL_PROFILES: frozenset[str] = frozenset(
    {"reasonix", "codex", "claude", "opencode", "chatgpt_pro"}
)

# Canonical aliases.
PROFILE_ALIASES: dict[str, str] = {
    "deepseek": "reasonix",
    "opus": "claude",
    "fable": "claude",
}


@dataclass
class ValidationResult:
    ok: bool
    error: str | None = None
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    job_created: bool = False
    profile: str | None = None
    operation: str | None = None


@dataclass
class StartRequest:
    operation: str
    profile: str
    transport: str
    autonomy: str
    sensitivity: str
    model: str
    prompt: str = ""
