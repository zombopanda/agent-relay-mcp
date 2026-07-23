# Changelog

All notable changes to Agent Relay MCP.

## [0.1.3] — Unreleased

### Added
- Public product identity: `agent-relay-mcp` (repo, PyPI, npm, CLI).
- Environment variable migration: `AGENT_RELAY_*` replaces `AGENT_HARNESS_*` with backward-compatible deprecation shim.
- Python 3.11, 3.12, and 3.13 support.
- Public README with quickstart, tool table, support matrix, troubleshooting codes.
- `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`, MIT `LICENSE`.
- `AGENTS.md` contributor code contract.
- npm package reduced to logic-free `uvx` launcher.
- Public GitHub Actions CI: Python matrix, package audits, secret scan, CodeQL, Dependabot.
- Protected maintainer workflows for live provider gates and trusted release publishing.
- Package content audits excluding internal results, benchmarks, private paths, and telemetry.

### Changed
- Import package renamed: `agent_harness_mcp` → `agent_relay_mcp`.
- Distribution name: `agent-harness-mcp` → `agent-relay-mcp`.
- State directory default: `~/.local/state/agent-relay-mcp`.
- All env vars use `AGENT_RELAY_` prefix.
- npm package: `@pandenko/agent-harness-mcp` → `agent-relay-mcp` (no scope).
- Removed private registry metadata from public package/docs.
- Removed `@pandenko` branding from public-facing files.

### Fixed
- `requires-python` lowered from `>=3.13` to `>=3.11` after compatibility verification.

## [0.1.2] and earlier — Internal

Pre-release internal versions. Not published publicly. See private repository history.
