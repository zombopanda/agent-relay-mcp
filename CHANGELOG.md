# Changelog

All notable changes to Agent Crossbar.

## [0.2.0] — Unreleased

### Added
- Public product identity: `agent-crossbar` (repo, PyPI, npm, CLI).
- Environment variable migration: `AGENT_CROSSBAR_*` replaces `AGENT_HARNESS_*` with backward-compatible deprecation shim.
- Python 3.11, 3.12, and 3.13 support.
- Public README with quickstart, tool table, support matrix, troubleshooting codes.
- `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`, MIT `LICENSE`.
- `AGENTS.md` contributor code contract.
- npm package reduced to logic-free `uvx` launcher.
- Public GitHub Actions CI: Python matrix, package audits, secret scan, CodeQL, Dependabot.
- Protected maintainer workflows for live provider gates and trusted release publishing.
- Package content audits excluding internal results, benchmarks, private paths, and telemetry.

### Changed
- Public identity renamed from the rejected `Agent Relay MCP` /
  `agent-relay-mcp` name to `Agent Crossbar` / `agent-crossbar`.
- Import package renamed: `agent_harness_mcp` → `agent_crossbar`.
- Distribution name: `agent-harness-mcp` → `agent-crossbar`.
- State directory default: `~/.local/state/agent-crossbar`.
- All env vars use `AGENT_CROSSBAR_` prefix.
- npm package: `@pandenko/agent-harness-mcp` → `agent-crossbar` (no scope).
- Removed private registry metadata from public package/docs.
- Removed `@pandenko` branding from public-facing files.

### Fixed
- `requires-python` lowered from `>=3.13` to `>=3.11` after compatibility verification.

### Migration
- The accidentally published `agent-relay-mcp==0.1.3` release is superseded by
  `agent-crossbar==0.2.0`. It remains available only as a yanked historical
  release so the abandoned namespace cannot be silently reused.

## [0.1.2] and earlier — Internal

Pre-release internal versions. Not published publicly. See private repository history.
