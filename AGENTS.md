# Agent Crossbar — Contributor Code Rules

These rules apply to code contributions. They are intentionally concise and focused on the public contract.

## Public Contract (Provider-Neutral)

1. **No top-level provider-specific fields.** The public API (`agent_start`, `job_result`, tool schemas) MUST NOT expose fields that only apply to a single provider. Provider-specific metadata lives in per-profile capability entries.

2. **The 8-tool MCP surface is locked.** Adding or removing a tool requires a design discussion and version bump. No hidden tools. No deprecated aliases.

3. **Stable error codes.** Error codes documented in the README troubleshooting table MUST NOT change semantics in a patch version. New codes may be added in minor versions.

4. **`agent_start` schema is provider-neutral and minimal.** The only public fields are: `profile`, `prompt`, `task`, `interactive`, `model`, `effort`, `cwd`, `scope`, `max_runtime_sec`, plus standard client metadata (`client`, `client_name`, `client_version`, `client_session_id`). No transport enum, no provider-specific routing hints.

5. **`interactive` is a boolean.** The public schema exposes `interactive` as a single boolean. No transport enum, no public transport field. Transport selection is an internal adapter concern.

6. **Forbidden (dead) public fields.** The following fields MUST NOT appear in the `agent_start` signature or any shipped schema: `external_context`, `budget_usd`, `text_subtype`, `review_target`, `context_target`, `full_local`. No compatibility shims, no deprecated aliases for these.

## Architecture

7. **Per-profile adapter modules.** Each provider gets one bounded module under `agent_crossbar/adapters/` implementing `ProviderAdapter` from `base.py`. Adapter modules MUST NOT import from each other.

8. **Core modules are provider-agnostic.** `server.py`, `jobs.py`, `validation.py`, `envelope.py`, `readiness.py` MUST NOT contain provider-specific branching. Provider behavior is injected through adapter lookups.

9. **Per-profile capabilities/models live in separate profile modules.** Each profile under `agent_crossbar/profiles/` owns its capabilities, models, and default configuration. Model lists MUST come from CLI discovery (`discovery.py`), not hardcoded. Profile modules MUST NOT import from each other.

10. **No compatibility aliases for removed fields.** Removed fields (`transport`, `autonomy`, `sensitivity`, `sanitized_context_only`, `timeout_sec`, etc.) MUST NOT have runtime compatibility shims, aliases, or warning-based remapping. They are simply absent.

11. **Readiness probes are non-mutating and cached.** Probes inspect state, never change it. Results cache for 60 seconds. Registration alone never produces `ready`.

## Testing

12. **TDD for provider changes.** Any new provider adapter, capability, or transport MUST include:
    - Unit tests proving validation, schema conformance, and error paths (no live provider).
    - A passing live provider gate (maintainer-only workflow) on every claimed operation/transport combination.

13. **No fake capabilities or models.** Model lists and capability declarations MUST come from live provider discovery or documentation references. Do not invent capabilities.

14. **Deterministic CI.** All tests in public PR CI MUST pass without provider credentials. Provider-dependent tests use `pytest.skip` when credentials are absent.

## Package Hygiene

15. **Public artifacts exclude internal content.** Benchmark results, `.reasonix/`, `.memsearch/`, personal paths, private URLs, and handoff files MUST NOT appear in wheel/sdist/npm tarball.
