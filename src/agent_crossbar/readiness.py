"""Unified provider readiness probes with bounded cache.

Provides the shared readiness schema, provider-specific non-mutating
probes, a TTL-bounded in-process cache, and the public ``probe_profile``
entry point used by both ``profile_health`` (MCP tool) and
``agent-crossbar doctor`` (CLI).

Design constraints:
- Probes are SAFE and NON-MUTATING — they inspect state, never change it.
- Every probe returns a stable state, error_code, and actionable remediation.
- Registration alone SHALL NOT produce ``ready``.
- Secrets are never included in evidence.
"""

from __future__ import annotations

import platform
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any

from .envelope import sanitize_diagnostic_text

# ── Constants ───────────────────────────────────────────────────────────────

PROBE_CACHE_TTL_SECONDS = 60  # 1 minute — cheap enough for repeated calls
VALID_STATES = frozenset(
    {
        "ready",
        "needs_auth",
        "missing_binary",
        "unsupported_os",
        "misconfigured",
        "degraded",
    }
)
VALID_TIERS = frozenset({"supported", "experimental"})


# ── ProbeResult — intermediate type returned by raw probe functions ──────────


@dataclass(frozen=True)
class ProbeResult:
    """Raw result from a single provider probe.

    This is the intermediate type returned by ``check_*_readiness()``
    functions.  It carries the narrow probe outcome before it is wrapped
    in the full ``ReadinessResult`` envelope with profile metadata.
    """

    state: str
    authenticated: bool
    auth_mode: str | None = None
    billing_mode: str | None = None
    subscription_type: str | None = None
    error_code: str | None = None
    remediation: str | None = None
    evidence: str | None = None
    version: str | None = None

    def __post_init__(self) -> None:
        if self.state not in VALID_STATES:
            raise ValueError(f"Invalid probe state {self.state!r}. Valid: {sorted(VALID_STATES)}")

    def to_readiness(self, profile: str, support_tier: str) -> ReadinessResult:
        """Wrap this ProbeResult into a full ReadinessResult.

        Evidence and remediation may originate from raw provider output or
        exception text (e.g. ``ProbeResult.from_exception``) — sanitize both
        here, at the single point every ``ReadinessResult`` is constructed,
        so no caller can forget to scrub secrets before the result is
        serialized or returned.
        """
        return ReadinessResult(
            profile=profile,
            state=self.state,
            support_tier=support_tier,
            authenticated=self.authenticated,
            auth_mode=self.auth_mode,
            billing_mode=self.billing_mode,
            subscription_type=self.subscription_type,
            error_code=self.error_code,
            remediation=sanitize_diagnostic_text(self.remediation)
            if self.remediation is not None
            else None,
            evidence=sanitize_diagnostic_text(self.evidence) if self.evidence is not None else None,
            version=self.version,
            probe_version=1,
            timestamp=time.time(),
        )

    @classmethod
    def from_file_not_found(cls, profile: str, exc: FileNotFoundError) -> ProbeResult:
        """Create a missing_binary result from a FileNotFoundError."""
        binary = str(exc.filename) if exc.filename else profile
        return cls(
            state="missing_binary",
            authenticated=False,
            error_code=f"{profile}_missing",
            remediation=f"`{binary}` is not installed or not on PATH. "
            f"Install the {profile} CLI and retry.",
            evidence=str(exc),
        )

    @classmethod
    def from_exception(cls, profile: str, exc: Exception) -> ProbeResult:
        """Create a misconfigured result from a generic exception."""
        return cls(
            state="misconfigured",
            authenticated=False,
            error_code=f"{profile}_probe_failed",
            remediation=f"Failed to probe {profile}: {exc}",
            evidence=str(exc)[:500],
        )

    @classmethod
    def from_process_error(cls, profile: str, error_code: str, remediation: str) -> ProbeResult:
        """Create a misconfigured result for a broken binary."""
        return cls(
            state="misconfigured",
            authenticated=False,
            error_code=error_code,
            remediation=remediation,
        )


# ── ReadinessResult — the public readiness envelope ─────────────────────────


@dataclass(frozen=True)
class ReadinessResult:
    """Structured readiness for one provider profile.

    This is the public type returned by ``probe_profile()`` and surfaced
    in ``profile_health`` and ``agent-crossbar doctor``.
    """

    profile: str
    state: str
    support_tier: str
    authenticated: bool
    error_code: str | None = None
    remediation: str | None = None
    evidence: str | None = None
    auth_mode: str | None = None
    billing_mode: str | None = None
    subscription_type: str | None = None
    version: str | None = None
    probe_version: int = 1
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.state not in VALID_STATES:
            raise ValueError(
                f"Invalid readiness state {self.state!r}. Valid: {sorted(VALID_STATES)}"
            )
        if self.support_tier not in VALID_TIERS:
            raise ValueError(
                f"Invalid support tier {self.support_tier!r}. Valid: {sorted(VALID_TIERS)}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON responses."""
        return {
            "profile": self.profile,
            "state": self.state,
            "support_tier": self.support_tier,
            "authenticated": self.authenticated,
            "error_code": self.error_code,
            "remediation": self.remediation,
            "evidence": self.evidence,
            "auth_mode": self.auth_mode,
            "billing_mode": self.billing_mode,
            "subscription_type": self.subscription_type,
            "version": self.version,
            "probe_version": self.probe_version,
            "timestamp": self.timestamp,
        }


# ── Runner protocol (narrow, injectable) ────────────────────────────────────


class _SubprocessRunner:
    """Thin wrapper over subprocess.run for injectability in tests."""

    def run(
        self,
        args: list[str],
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
            check=False,
        )


# ── Provider probes ─────────────────────────────────────────────────────────


def check_claude_readiness(runner: Any = None) -> ProbeResult:
    """Probe Claude Code readiness via ``claude auth status --json``.

    Non-mutating — only reads auth state.
    """
    if runner is None:
        runner = _SubprocessRunner()

    try:
        result = runner.run(["claude", "auth", "status", "--json"], timeout=15)
    except FileNotFoundError as exc:
        return ProbeResult.from_file_not_found("claude", exc)
    except Exception as exc:
        return ProbeResult.from_exception("claude", exc)

    if result.returncode != 0:
        return ProbeResult(
            state="needs_auth",
            authenticated=False,
            error_code="auth_probe_failed",
            remediation="Claude auth status probe failed. Run `claude auth login`.",
            evidence=(result.stderr or result.stdout)[:500],
        )

    import json

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return ProbeResult(
            state="needs_auth",
            authenticated=False,
            error_code="invalid_auth_status",
            remediation="Claude auth status returned invalid JSON. Run `claude doctor`.",
            evidence=result.stdout[:500],
        )

    if not payload.get("loggedIn"):
        return ProbeResult(
            state="needs_auth",
            authenticated=False,
            error_code="not_authenticated",
            remediation="Run `claude auth login`.",
            evidence="Claude reports loggedIn=false.",
        )

    method = str(payload.get("authMethod") or "unknown")
    api_key = method in {"api_key", "console"}
    return ProbeResult(
        state="ready",
        authenticated=True,
        auth_mode="api_key" if api_key else "subscription",
        billing_mode="api" if api_key else "subscription_quota",
        subscription_type=str(payload["subscriptionType"])
        if payload.get("subscriptionType")
        else None,
        evidence=f"authMethod={method}; apiProvider={payload.get('apiProvider', 'unknown')}",
    )


def check_codex_readiness(runner: Any = None) -> ProbeResult:
    """Probe Codex readiness: pnpm + codex binary + ``codex login status``.

    Read-only — never installs packages or hits the network.
    The pinned ACP bridge (@agentclientprotocol/codex-acp@1.1.7) is a
    launch-time dependency verified at agent_start time, not by the doctor.
    """
    if runner is None:
        runner = _SubprocessRunner()

    # Step 1: pnpm
    try:
        pnpm_result = runner.run(["pnpm", "--version"], timeout=10)
    except FileNotFoundError:
        return ProbeResult(
            state="missing_binary",
            authenticated=False,
            error_code="pnpm_missing",
            remediation="pnpm is not installed. Install pnpm (https://pnpm.io/installation).",
        )
    except Exception as exc:
        return ProbeResult.from_exception("codex", exc)

    if pnpm_result.returncode != 0:
        return ProbeResult.from_process_error(
            "codex", "pnpm_broken", "pnpm is present but broken. Reinstall pnpm."
        )

    # Step 2: codex binary
    try:
        codex_result = runner.run(["codex", "--version"], timeout=10)
    except FileNotFoundError:
        return ProbeResult(
            state="missing_binary",
            authenticated=False,
            error_code="codex_missing",
            remediation="codex CLI is not installed. Install the Codex CLI.",
        )
    except Exception as exc:
        return ProbeResult.from_exception("codex", exc)

    if codex_result.returncode != 0:
        return ProbeResult.from_process_error(
            "codex", "codex_broken", "codex CLI is present but broken. Reinstall the Codex CLI."
        )

    codex_version_line = codex_result.stdout.strip().split("\n")[0] if codex_result.stdout else None

    # Step 3: codex login status (read-only auth probe)
    try:
        login_result = runner.run(["codex", "login", "status"], timeout=15)
    except FileNotFoundError:
        # codex binary exists but 'login status' subcommand missing —
        # treat as needs_auth since we cannot verify
        return ProbeResult(
            state="needs_auth",
            authenticated=False,
            error_code="codex_login_status_missing",
            remediation="`codex login status` is not available. Run `codex login`.",
            evidence=f"codex={codex_version_line}",
        )
    except Exception as exc:
        return ProbeResult.from_exception("codex", exc)

    # codex login status writes to stderr, not stdout — check both
    login_output = ((login_result.stdout or "") + (login_result.stderr or "")).strip()
    login_stderr = (login_result.stderr or "").strip()

    if login_result.returncode != 0:
        return ProbeResult(
            state="needs_auth",
            authenticated=False,
            error_code="codex_login_status_failed",
            remediation="`codex login status` failed. Run `codex login` to authenticate.",
            evidence=f"codex={codex_version_line}; login_status_exit={login_result.returncode}; "
            f"stderr={login_stderr[:200]}",
        )

    # Parse: "Logged in using ChatGPT" or similar
    # Watch out: "Not logged in" contains the substring "logged in".
    logged_in = "logged in" in login_output.lower() and "not logged in" not in login_output.lower()

    if not logged_in:
        return ProbeResult(
            state="needs_auth",
            authenticated=False,
            error_code="codex_not_authenticated",
            remediation="Run `codex login` to authenticate.",
            evidence=f"codex={codex_version_line}; login_status={login_output[:200]}",
        )

    auth_mode, billing_mode = _classify_codex_auth(login_output)

    return ProbeResult(
        state="ready",
        authenticated=True,
        auth_mode=auth_mode,
        billing_mode=billing_mode,
        evidence=f"codex={codex_version_line}; login_status={login_output[:200]}",
    )


def _classify_codex_auth(login_output: str) -> tuple[str, str]:
    """Classify a logged-in ``codex login status`` message into (auth_mode, billing_mode).

    Never returns null — an unrecognized (but logged-in) message is
    reported as an explicit ``"unknown"`` mode rather than omitted.
    """
    lowered = login_output.lower()
    if "chatgpt" in lowered:
        return "chatgpt_subscription", "subscription_quota"
    if "api key" in lowered or "apikey" in lowered:
        return "api_key", "api"
    return "unknown", "unknown"


def check_opencode_readiness(runner: Any = None) -> ProbeResult:
    """Probe OpenCode readiness: opencode binary + ``opencode auth list``.

    OpenCode uses native ACP — no pnpm dependency for the doctor probe.
    Read-only — never installs packages or hits the network.
    The native ``opencode acp`` subcommand is verified at agent_start time
    via ACP preflight, not by the doctor.

    ``opencode auth list`` output may contain ANSI escapes. A credential
    list proves configured providers; absence may still allow OpenCode
    free defaults, so an empty list does not block readiness.
    """
    if runner is None:
        runner = _SubprocessRunner()

    # Step 1: opencode binary
    try:
        oc_result = runner.run(["opencode", "--version"], timeout=10)
    except FileNotFoundError:
        return ProbeResult(
            state="missing_binary",
            authenticated=False,
            error_code="opencode_missing",
            remediation="opencode CLI is not installed. Install the OpenCode CLI.",
        )
    except Exception as exc:
        return ProbeResult.from_exception("opencode", exc)

    if oc_result.returncode != 0:
        return ProbeResult.from_process_error(
            "opencode",
            "opencode_broken",
            "opencode CLI is present but broken. Reinstall the OpenCode CLI.",
        )

    oc_version_line = oc_result.stdout.strip().split("\n")[0] if oc_result.stdout else None

    # Step 2: opencode auth list (read-only auth probe)
    import re as _re

    try:
        auth_result = runner.run(["opencode", "auth", "list"], timeout=15)
    except Exception as exc:
        # The auth probe itself failed to run — we cannot prove or disprove
        # credentials from this, so never infer authenticated=True from
        # binary presence alone. Report honestly as degraded/unverified.
        return ProbeResult(
            state="degraded",
            authenticated=False,
            error_code="opencode_auth_unverified",
            remediation="Run `opencode auth list` manually to verify authentication.",
            evidence=f"opencode={oc_version_line}; auth_list probe error: {exc}",
        )

    auth_stdout = auth_result.stdout or ""
    auth_stderr = auth_result.stderr or ""

    # Parse auth list — strip ANSI escapes, look for credential indicators
    # The output format is: lines with ● ProviderName type
    # We look for lines containing known provider names after stripping ANSI
    ansi_stripped = _re.sub(r"\x1b\[[0-9;]*m", "", auth_stdout)
    # Count credential entries: "● " or digit + " credentials" summary line
    has_credentials = bool(_re.search(r"●\s+\S+", ansi_stripped))
    credential_count_match = _re.search(r"(\d+)\s+credentials?", ansi_stripped)

    if has_credentials or (credential_count_match and int(credential_count_match.group(1)) > 0):
        count = credential_count_match.group(1) if credential_count_match else "?"
        return ProbeResult(
            state="ready",
            authenticated=True,
            auth_mode="providers_configured",
            billing_mode="provider_dependent",
            evidence=f"opencode={oc_version_line}; auth_list={count}_providers",
        )

    # A non-zero exit proves nothing — it neither confirms credentials nor
    # proves the empty-list free-defaults case, so it must not be reported
    # as ready. Only a successful (exit 0) empty list may be ready.
    if auth_result.returncode != 0:
        return ProbeResult(
            state="degraded",
            authenticated=False,
            error_code="opencode_auth_list_failed",
            remediation=(
                "`opencode auth list` exited non-zero — cannot verify configured "
                "providers or free-default availability. Run `opencode auth list` "
                "manually, or `opencode auth login` to configure a provider."
            ),
            evidence=f"opencode={oc_version_line}; auth_list_exit={auth_result.returncode}; "
            f"stderr={auth_stderr[:200]}",
        )

    # Auth list succeeded but reported no credentials — opencode may still
    # work via free defaults, so we don't block readiness, but authenticated
    # must stay honest (False) rather than inferred from binary presence alone.
    return ProbeResult(
        state="ready",
        authenticated=False,
        auth_mode="free_defaults",
        billing_mode="free_defaults",
        evidence=f"opencode={oc_version_line}; auth_list=empty; unauthenticated free defaults",
    )


def check_reasonix_readiness(runner: Any = None) -> ProbeResult:
    """Probe Reasonix readiness via ``reasonix doctor --json``.

    Reasonix is an **experimental** adapter — binary presence alone
    SHALL NOT produce ``ready``.  The probe parses the doctor's
    structured ``api-key`` and ``api-reach`` checks (never the key
    value itself) to prove authentication.  When the doctor output is
    unavailable or unparseable, the probe returns ``degraded`` with an
    actionable remediation rather than guessing ``ready``.
    """
    if runner is None:
        runner = _SubprocessRunner()

    try:
        version_result = runner.run(["reasonix", "--version"], timeout=10)
    except FileNotFoundError:
        return ProbeResult(
            state="missing_binary",
            authenticated=False,
            error_code="reasonix_missing",
            remediation="reasonix is not installed. Install the Reasonix CLI.",
        )
    except Exception as exc:
        return ProbeResult.from_exception("reasonix", exc)

    if version_result.returncode != 0:
        return ProbeResult.from_process_error(
            "reasonix",
            "reasonix_broken",
            "reasonix is present but broken. Reinstall the Reasonix CLI.",
        )

    version = version_result.stdout.strip().split("\n")[0] if version_result.stdout else None

    try:
        doctor_result = runner.run(["reasonix", "doctor", "--json"], timeout=20)
    except Exception as exc:
        return ProbeResult(
            state="degraded",
            authenticated=False,
            error_code="reasonix_auth_unverified",
            remediation="Run `reasonix doctor` and confirm the api-key and api-reach checks pass.",
            evidence=f"reasonix={version}; doctor probe error: {exc}",
            version=version,
        )

    if doctor_result.returncode != 0:
        return ProbeResult(
            state="degraded",
            authenticated=False,
            error_code="reasonix_auth_unverified",
            remediation="Run `reasonix doctor` and confirm the api-key and api-reach checks pass.",
            evidence=f"reasonix={version}; doctor exited {doctor_result.returncode}",
            version=version,
        )

    import json

    try:
        payload = json.loads(doctor_result.stdout)
    except json.JSONDecodeError:
        return ProbeResult(
            state="degraded",
            authenticated=False,
            error_code="reasonix_auth_unverified",
            remediation="Run `reasonix doctor` and confirm the api-key and api-reach checks pass.",
            evidence=f"reasonix={version}; doctor returned non-JSON output",
            version=version,
        )

    checks = {
        c.get("id"): c for c in payload.get("checks", []) if isinstance(c, dict) and c.get("id")
    }
    api_key_check = checks.get("api-key")
    api_reach_check = checks.get("api-reach")

    if api_key_check is None or api_reach_check is None:
        return ProbeResult(
            state="degraded",
            authenticated=False,
            error_code="reasonix_auth_unverified",
            remediation=(
                "`reasonix doctor --json` did not report api-key/api-reach checks. "
                "Run `reasonix doctor` manually to verify authentication."
            ),
            evidence=f"reasonix={version}; doctor checks={sorted(checks)}",
            version=version,
        )

    if api_key_check.get("status") != "ok":
        return ProbeResult(
            state="needs_auth",
            authenticated=False,
            error_code="reasonix_not_authenticated",
            remediation="Run `reasonix setup` to configure your DeepSeek API key.",
            evidence=f"reasonix={version}; api-key={api_key_check.get('message')}",
            version=version,
        )

    if api_reach_check.get("status") != "ok":
        return ProbeResult(
            state="needs_auth",
            authenticated=False,
            error_code="reasonix_api_unreachable",
            remediation=(
                "API key is configured but the DeepSeek API is unreachable. "
                "Check network connectivity and key validity: `reasonix doctor`."
            ),
            evidence=f"reasonix={version}; api-reach={api_reach_check.get('message')}",
            version=version,
        )

    return ProbeResult(
        state="ready",
        authenticated=True,
        auth_mode="api_key",
        billing_mode="api",
        version=version,
        evidence=(
            f"reasonix={version}; api-key={api_key_check.get('message')}; "
            f"api-reach={api_reach_check.get('message')}"
        ),
    )


def check_chatgpt_pro_readiness(runner: Any = None) -> ProbeResult:
    """Probe ChatGPT Pro readiness: macOS-only, truthful auth/binary check.

    ChatGPT Pro requires macOS with the ChatGPT desktop application.
    On non-macOS, returns ``unsupported_os``.
    On macOS, returns ``degraded`` — we cannot safely prove authentication
    or application state via a non-mutating probe. The caller must perform
    a manual gate (launch the ChatGPT app and sign in).
    """
    system = platform.system()
    if system != "Darwin":
        return ProbeResult(
            state="unsupported_os",
            authenticated=False,
            error_code="unsupported_os",
            remediation=(
                f"ChatGPT Pro is only supported on macOS. "
                f"Current OS: {system}. Use codex, claude, or opencode instead."
            ),
            evidence=f"platform={system}",
        )
    return ProbeResult(
        state="degraded",
        authenticated=False,
        error_code="chatgpt_pro_manual_gate",
        remediation=(
            "ChatGPT Pro readiness cannot be automatically verified. "
            "Ensure the native ChatGPT desktop app is installed, launched, "
            "and signed in with a Pro subscription. Then retry."
        ),
        evidence="macOS detected — manual gate required for ChatGPT Pro GUI automation.",
    )


# ── Cache ───────────────────────────────────────────────────────────────────


def _cache_key(profile: str) -> str:
    return f"readiness:{profile}"


class _ReadinessCache:
    """In-process bounded cache for readiness probe results.

    Thread-safe.  Entries expire after PROBE_CACHE_TTL_SECONDS.
    """

    def __init__(self) -> None:
        self._entries: dict[str, ReadinessResult] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> ReadinessResult | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if time.time() - entry.timestamp > PROBE_CACHE_TTL_SECONDS:
                del self._entries[key]
                return None
            return entry

    def put(self, key: str, result: ReadinessResult) -> None:
        with self._lock:
            self._entries[key] = result

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


# Module-level cache instance
readiness_cache = _ReadinessCache()


# ── Public API ──────────────────────────────────────────────────────────────


def probe_profile(
    profile: str,
    _runner: Any = None,
    *,
    use_cache: bool = True,
) -> ReadinessResult:
    """Run readiness probes for *profile* and return a ReadinessResult.

    Uses an in-process cache (TTL: PROBE_CACHE_TTL_SECONDS) when
    *use_cache* is True.

    *profile* must be a canonical profile name (codex, claude, opencode,
    reasonix, chatgpt_pro).
    """
    from agent_crossbar.adapters.registry import ADAPTERS

    if profile not in ADAPTERS:
        raise ValueError(f"Unknown profile: {profile!r}")

    adapter = ADAPTERS[profile]
    support_tier = adapter.support_tier

    key = _cache_key(profile)
    if use_cache:
        cached = readiness_cache.get(key)
        if cached is not None:
            return cached

    # Run the provider-specific probe
    if profile == "claude":
        pr = check_claude_readiness(_runner)
    elif profile == "codex":
        pr = check_codex_readiness(_runner)
    elif profile == "opencode":
        pr = check_opencode_readiness(_runner)
    elif profile == "reasonix":
        pr = check_reasonix_readiness(_runner)
    elif profile == "chatgpt_pro":
        pr = check_chatgpt_pro_readiness(_runner)
    else:
        raise ValueError(f"No probe for profile: {profile!r}")

    result = pr.to_readiness(profile, support_tier)

    if use_cache:
        readiness_cache.put(key, result)

    return result


def refresh_readiness(profile: str, _runner: Any = None) -> ReadinessResult:
    """Force a fresh readiness probe, bypassing the cache.

    Use this to populate or update cache entries explicitly.
    """
    return probe_profile(profile, _runner=_runner, use_cache=False)


def probe_all_profiles(
    _runner: Any = None,
    *,
    use_cache: bool = True,
) -> dict[str, ReadinessResult]:
    """Probe all canonical profiles and return a dict of results.

    Profiles whose probes crash are returned as ``misconfigured`` results
    with a stable error code and remediation — never silently omitted.
    """
    from agent_crossbar.profiles import list_profiles

    results: dict[str, ReadinessResult] = {}
    for profile in list_profiles():
        try:
            results[profile] = probe_profile(profile, _runner=_runner, use_cache=use_cache)
        except Exception as exc:
            # Return a misconfigured result instead of silently omitting
            pr = ProbeResult(
                state="misconfigured",
                authenticated=False,
                error_code=f"{profile}_probe_crashed",
                remediation=f"Readiness probe for {profile} crashed: {exc}",
                evidence=str(exc)[:500],
            )
            # Derive support tier from adapter
            try:
                from agent_crossbar.adapters.registry import ADAPTERS

                tier = ADAPTERS[profile].support_tier
            except Exception:
                tier = "experimental"
            results[profile] = pr.to_readiness(profile, tier)
    return results
