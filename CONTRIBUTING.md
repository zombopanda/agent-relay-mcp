# Contributing to Agent Crossbar

Thanks for your interest! Agent Crossbar is an experimental developer preview.

## Development Environment

```bash
git clone https://github.com/zombopanda/agent-crossbar
cd agent-crossbar
uv sync --extra test
```

Run tests:

```bash
uv run pytest tests/ -q
```

## Code Rules

See [AGENTS.md](AGENTS.md) for the contributor code contract.

## Pull Requests

1. Fork the repository.
2. Create a feature branch.
3. Run the full test suite (`uv run pytest tests/ -q`).
4. If your change touches provider behavior, run the live provider gate (maintainers only — requires credentials).
5. Open a PR against `main`.

**PR CI** runs on standard GitHub-hosted runners (Ubuntu + macOS) with read-only permissions. No provider credentials are available in PR workflows — provider-dependent tests are skipped.

## Public Contract & Contributor Rules

See [AGENTS.md](AGENTS.md) for the full contributor code contract. This is the canonical reference — do not duplicate its policy here. Key points:

- `agent_start` has a provider-neutral minimal schema (10 fields + client metadata).
- `interactive` is boolean-only (no public transport enum).
- Forbidden public fields: `external_context`, `budget_usd`, `text_subtype`, `review_target`, `context_target`, `full_local`.
- Model lists come from CLI discovery, not hardcoded lists.
- No compatibility aliases for removed fields.
- All CI tests must pass without provider credentials.

## Release Process

Maintainers trigger releases via signed tag → PyPI trusted publishing. See `.github/workflows/release.yml`.

## Compatibility

Agent Crossbar follows an experimental-preview compatibility policy. Patch versions (0.1.x) preserve stable error codes and tool signatures. Minor versions may change APIs.
