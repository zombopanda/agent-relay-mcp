"""Model-discovery orchestrator — ties cache, runner, and adapters for health checks."""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from .adapters.base import ModelCatalog, ModelInfo
from .adapters.codex import CodexAdapter
from .adapters.opencode import OpencodeAdapter
from .discovery_runner import DiscoveryProcess, DiscoveryRun
from .envelope import sanitize_diagnostic_text
from .model_cache import CACHE_TTL_SECONDS, cache_get_or_fetch, read_cache_any


class _DiscoveryDiagnostics:
    """Thread-safe bounded store of the last sanitized live-discovery failure per profile.

    ``cached_models_for_listing`` falls back to static models on any live-discovery
    failure — this store preserves *why* it fell back so ``profile_health`` can
    surface an honest diagnostic instead of a generic "nothing cached yet"
    message. Cleared per-profile on the next successful discovery.
    """

    def __init__(self) -> None:
        self._entries: dict[str, str] = {}
        self._lock = threading.Lock()

    def record(self, profile: str, message: str) -> None:
        sanitized = sanitize_diagnostic_text(message)
        with self._lock:
            self._entries[profile] = sanitized

    def clear_profile(self, profile: str) -> None:
        with self._lock:
            self._entries.pop(profile, None)

    def get(self, profile: str) -> str | None:
        with self._lock:
            return self._entries.get(profile)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


# Module-level store, mirroring the readiness_cache pattern in readiness.py
discovery_diagnostics = _DiscoveryDiagnostics()


def _catalog_to_dict(catalog: ModelCatalog) -> dict[str, Any]:
    """Serialize a ModelCatalog to a plain dict for the cache."""
    return {
        "models": list(catalog.models),
        "default_model": catalog.default_model,
        "native_efforts": list(catalog.native_efforts),
        "model_info": [
            {
                "id": mi.id,
                "supported_efforts": list(mi.supported_efforts),
                "default_effort": mi.default_effort,
            }
            for mi in catalog.model_info
        ],
        "error": catalog.error,
        "source": catalog.source,
    }


def _dict_to_catalog(
    data: dict[str, Any],
    source: str,
    version: str | None,
    fetched_at: float | None,
    *,
    cache_hit: bool = False,
) -> ModelCatalog:
    """Deserialize a cache dict back to a ModelCatalog."""
    model_info_raw = data.get("model_info", [])
    return ModelCatalog(
        models=tuple(data.get("models", [])),
        default_model=data.get("default_model"),
        native_efforts=tuple(data.get("native_efforts", [])),
        source=data.get("source", source),
        error=data.get("error"),
        model_info=tuple(
            ModelInfo(
                id=mi["id"],
                supported_efforts=tuple(mi.get("supported_efforts", [])),
                default_effort=mi.get("default_effort"),
            )
            for mi in model_info_raw
        ),
        cli_version=version,
        fetched_at=fetched_at,
        stale=bool(data.get("stale", False)),
        cache_hit=cache_hit,
    )


class _BoundedSubprocessRunner:
    """An argv-only subprocess runner implementing DiscoveryProcess."""

    def run(
        self,
        args: list[str],
        *,
        timeout: float | None = None,
        cwd: str | None = None,
    ) -> DiscoveryRun:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            check=False,
        )
        return DiscoveryRun(completed.returncode, completed.stdout, completed.stderr)


def _get_cli_version(profile: str) -> str:
    """Try to determine the CLI version for cache-key purposes."""
    runner = _BoundedSubprocessRunner()
    binary_map = {"codex": "codex", "opencode": "opencode", "claude": "claude"}
    binary = binary_map.get(profile)
    if binary is None:
        return "unknown"
    try:
        result = runner.run([binary, "--version"], timeout=10)
        if result.returncode == 0:
            return result.stdout.strip().split("\n")[0]
    except Exception:
        pass
    return "unknown"


_PROFILES_WITH_DISCOVERY = frozenset({"codex", "opencode", "claude"})


def _fetch_codex(runner: DiscoveryProcess) -> dict[str, Any]:
    adapter = CodexAdapter()
    catalog = adapter.discover_models(runner)
    return _catalog_to_dict(catalog)


def _fetch_opencode(runner: DiscoveryProcess) -> dict[str, Any]:
    adapter = OpencodeAdapter()
    catalog = adapter.discover_models(runner)
    return _catalog_to_dict(catalog)


def _fetch_claude() -> dict[str, Any]:
    """Discover Claude models via the interactive /model picker PTY probe.

    The probe manages its own child process — no runner is needed.
    """
    from .adapters.claude import ClaudeAdapter

    adapter = ClaudeAdapter()
    catalog = adapter.discover_models()
    return _catalog_to_dict(catalog)


def discover_profile_models(
    state_root: Path,
    profile: str,
    *,
    refresh: bool = False,
) -> ModelCatalog:
    """Discover models for *profile* with caching.

    Profiles without live discovery (reasonix, chatgpt_pro) return
    an honest ``ModelCatalog`` with ``error`` set.
    """
    if profile not in _PROFILES_WITH_DISCOVERY:
        return ModelCatalog(
            models=(),
            default_model=None,
            native_efforts=(),
            source=f"{profile} model discovery unavailable",
            error=f"Profile '{profile}' does not support live model discovery.",
        )

    runner = _BoundedSubprocessRunner()
    version = _get_cli_version(profile)

    if profile == "codex":

        def fetcher():
            return _fetch_codex(runner)
    elif profile == "claude":
        fetcher = _fetch_claude  # probe manages its own process, no runner
    else:

        def fetcher():
            return _fetch_opencode(runner)

    data, from_cache = cache_get_or_fetch(
        state_root,
        profile,
        version,
        fetcher,
        refresh=refresh,
    )

    source = data.get("source", "unknown")
    catalog = _dict_to_catalog(
        data,
        source,
        version,
        data.get("fetched_at", time.time()),
        cache_hit=from_cache,
    )

    return catalog


def build_profile_health_entry(
    state_root: Path,
    profile: str,
    catalog: ModelCatalog | None = None,
    *,
    discovery_available: bool = True,
) -> dict[str, Any]:
    """Build a single profile health entry from a (possibly cached) catalog."""
    if profile in _PROFILES_WITH_DISCOVERY and discovery_available:
        if catalog is None:
            catalog = discover_profile_models(state_root, profile)
        return {
            "name": profile,
            "status": "registered",
            "runtime_checked": True,
            "discovery_available": True,
            "models": list(catalog.models),
            "default_model": catalog.default_model,
            "native_efforts": list(catalog.native_efforts),
            "model_info": [
                {
                    "id": mi.id,
                    "supported_efforts": list(mi.supported_efforts),
                    "default_effort": mi.default_effort,
                }
                for mi in catalog.model_info
            ],
            "source": catalog.source,
            "cli_version": catalog.cli_version,
            "fetched_at": catalog.fetched_at,
            "stale": catalog.stale,
            "cache_hit": catalog.cache_hit,
            "error": catalog.error,
        }
    else:
        return {
            "name": profile,
            "status": "registered",
            "runtime_checked": False,
            "discovery_available": False,
            "models": [],
            "error": f"Profile '{profile}' does not support live model discovery.",
        }


# ── profiles_list / profile_health model surfaces ────────────────────────────


def cached_models_for_listing(
    state_root: Path,
    profile: str,
    fallback_models: list[str],
    fallback_default: str | None,
) -> tuple[list[str], str | None]:
    """Return live-discovered models for *profile*, or the static fallback.

    Attempts bounded live discovery via ``discover_profile_models`` — which
    itself reads a fresh on-disk cache first, so a subsequent call after a
    successful discovery stays cache-only (no subprocess spawn) as long as
    the cache remains fresh and version-matched.  Falls back to
    (*fallback_models*, *fallback_default*) when the profile has no live
    discovery, the probe fails outright, or the discovered catalog itself
    carries a discovery error or empty model list — never surfaces an
    empty/unusable model list silently. The actual failure reason is not
    discarded: it is preserved (sanitized, bounded) in ``discovery_diagnostics``
    for ``profile_health`` to surface, and cleared on the next success.
    """
    if profile not in _PROFILES_WITH_DISCOVERY:
        return fallback_models, fallback_default

    try:
        catalog = discover_profile_models(state_root, profile)
    except Exception as exc:
        discovery_diagnostics.record(profile, f"{profile} live discovery crashed: {exc}")
        return fallback_models, fallback_default

    if not catalog.models or catalog.error:
        discovery_diagnostics.record(
            profile, catalog.error or f"{profile} discovery returned no models"
        )
        return fallback_models, fallback_default

    discovery_diagnostics.clear_profile(profile)
    return list(catalog.models), catalog.default_model or fallback_default


def live_profile_registry(state_root: Path) -> dict[str, Any]:
    """``profile_registry()`` with codex/claude/opencode models overlaid by a
    bounded live-discovery attempt (see ``cached_models_for_listing``).

    The three discovery-capable profiles are probed in parallel so
    aggregate latency is bounded by the slowest single probe rather than
    their sum — each probe already enforces its own subprocess timeout.
    A failed probe falls back to the static registry entry for that
    profile; a fresh, version-matched cache short-circuits back to a
    cache read with no subprocess spawn. Entry schema stays identical to
    ``profile_registry()`` (no keys added or removed), only
    ``models``/``default_model`` values may change.
    """
    from concurrent.futures import ThreadPoolExecutor

    from .profiles import profile_registry

    registry = profile_registry()

    with ThreadPoolExecutor(max_workers=max(len(registry), 1)) as pool:
        futures = {
            profile: pool.submit(
                cached_models_for_listing,
                state_root,
                profile,
                entry["models"],
                entry["default_model"],
            )
            for profile, entry in registry.items()
        }
        for profile, future in futures.items():
            models, default_model = future.result()
            registry[profile]["models"] = models
            registry[profile]["default_model"] = default_model

    return registry


def cached_profile_health_entry(state_root: Path, profile: str) -> dict[str, Any]:
    """Cache-only model-discovery entry for ``profile_health``.

    Unlike ``build_profile_health_entry``, this never spawns a live
    discovery subprocess — it surfaces whatever is already cached (even
    stale or version-mismatched), or an honest explanation when nothing
    has been discovered yet.  Keeps ``profile_health`` fast; the cache
    is populated by real usage (agent_start validation, `doctor`, or an
    explicit refresh).
    """
    if profile not in _PROFILES_WITH_DISCOVERY:
        return {
            "name": profile,
            "status": "registered",
            "runtime_checked": False,
            "discovery_available": False,
            "models": [],
            "error": f"Profile '{profile}' does not support live model discovery.",
        }

    version = _get_cli_version(profile)
    envelope = read_cache_any(state_root, profile)
    if envelope is None:
        last_failure = discovery_diagnostics.get(profile)
        error = (
            f"No cached model discovery yet — last discovery attempt failed: {last_failure}"
            if last_failure is not None
            else (
                "No cached model discovery yet — it is populated by starting a job "
                "or running `agent-relay-mcp doctor`."
            )
        )
        return {
            "name": profile,
            "status": "registered",
            "runtime_checked": False,
            "discovery_available": True,
            "models": [],
            "default_model": None,
            "native_efforts": [],
            "model_info": [],
            "source": None,
            "cli_version": version,
            "fetched_at": None,
            "stale": None,
            "cache_hit": False,
            "error": error,
        }

    data = envelope.get("data", {})
    fetched_at = envelope.get("fetched_at")
    stale = bool(fetched_at is None or time.time() - fetched_at > CACHE_TTL_SECONDS)
    last_failure = discovery_diagnostics.get(profile)
    if last_failure is not None:
        stale = True
    return {
        "name": profile,
        "status": "registered",
        "runtime_checked": True,
        "discovery_available": True,
        "models": list(data.get("models", [])),
        "default_model": data.get("default_model"),
        "native_efforts": list(data.get("native_efforts", [])),
        "model_info": data.get("model_info", []),
        "source": envelope.get("source", data.get("source")),
        "cli_version": version,
        "fetched_at": fetched_at,
        "stale": stale,
        "cache_hit": True,
        "error": last_failure if last_failure is not None else data.get("error"),
    }
