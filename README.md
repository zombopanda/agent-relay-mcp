# Agent Relay MCP

Delegate review, advice, text, and dev work to local coding agents — Codex, Claude, OpenCode — through a single MCP server. One `agent_start` call, one `job_result` answer.

**Experimental developer preview (v0.1.3).** APIs may change. Provider guarantees are qualified by live gates.

Expose to MCP clients with the server key `agents`.

## Demo

[Accessible transcript](demo/TRANSCRIPT.md) · [exact prompts](demo/PROMPTS.md) · [recording notes](demo/RECORDING.md)

## Ten-Minute Quickstart

### 1. Install

```bash
# Canonical: uvx pulls the latest PyPI release
uvx agent-relay-mcp

# Or via npm (thin launcher → delegates to uvx)
npx agent-relay-mcp
```

Prerequisites: [uv](https://docs.astral.sh/uv/getting-started/installation/) (for PyPI) or [Node.js](https://nodejs.org/) ≥ 20 (for npm launcher).

### 2. Check Readiness (doctor)

```bash
uvx agent-relay-mcp doctor
```

Verifies that supported provider CLIs are installed, authenticated, and runnable. A provider must be `ready` before jobs can be created.

### 3. Configure Your MCP Client

#### Codex MCP Config

```json
{
  "mcpServers": {
    "agents": {
      "command": "uvx",
      "args": ["agent-relay-mcp"]
    }
  }
}
```

#### Claude Code MCP Config

Claude Code uses the native `claude_bg` noninteractive backend (`claude` profile). Interactive and print mode are **disabled** in v0.1.3 because `claude -p` uses separate Agent SDK credit/metered billing — read [Claude Billing](#claude-subscription-vs-print-sdk-billing) below.

```json
{
  "mcpServers": {
    "agents": {
      "command": "uvx",
      "args": ["agent-relay-mcp"]
    }
  }
}
```

**Claude prerequisite**: authenticate with `claude auth login`. The doctor will report `needs_auth` until you do.

#### OpenCode MCP Config

```json
{
  "mcpServers": {
    "agents": {
      "command": "uvx",
      "args": ["agent-relay-mcp"]
    }
  }
}
```

### 4. First Review Flow

With the MCP server running, from any MCP client:

```
1. profiles_list                     → see available profiles and their tiers
2. profile_health                    → verify readiness before creating jobs
3. agent_start(
     profile="codex",
     prompt="Review my uncommitted changes for security issues.",
     task="review"
   )                                 → creates a review job
4. job_tail(job_id="<id>")           → stream real-time output
5. job_result(job_id="<id>")         → get final structured result
```

## Tools (8)

| # | Tool | Description |
|---|------|-------------|
| 1 | `agent_start` | Start an agent task (ask, review, or dev) in one call |
| 2 | `profiles_list` | List available agent profiles with support tiers and capabilities |
| 3 | `profile_health` | Run live readiness probes for all configured profiles |
| 4 | `job_tail` | Stream incremental job output by sequence number |
| 5 | `job_result` | Get final structured result, exit code, and summary |
| 6 | `job_send` | Send follow-up input to a running interactive job (not available for Claude bg) |
| 7 | `job_stop` | Stop a running job gracefully |
| 8 | `job_list` | List jobs scoped to the current client session |

**Exact 8-tool MCP surface.** No hidden tools, no deprecated aliases.

## Support Matrix

### Supported Profiles

| Profile | Tasks | Backend | OS | Default Model |
|---------|-------|---------|-----|---------------|
| `codex` | ask, review, dev | ACP one-shot (fallback to print for explicit effort) | macOS, Linux | gpt-5.6-sol |
| `claude` | ask, review, dev | Native `claude_bg` (noninteractive only; `claude -p` disabled; no `job_send`) | macOS, Linux | opus |
| `opencode` | ask, review, dev | ACP one-shot (fallback to print for explicit effort) | macOS, Linux | opencode/deepseek-v4-flash-free |

### Experimental (Installed, Not Guaranteed)

| Profile | Tasks | Interactive | Notes |
|---------|-------|-------------|-------|
| `reasonix` | ask, review, dev | false or true | Experimental TUI adapter; results use heuristic parsing |

Latest local experimental evidence (2026-07-23): the default
`deepseek-v4-flash` noninteractive ask gate received its live sentinel. This
result is informational and does not promote Reasonix to the supported tier.

### Provider Prerequisites

| Provider | Binary | Auth Check |
|----------|--------|-----------|
| Codex | `codex` CLI + `pnpm` | `codex login status` |
| Claude | `claude` CLI | `claude auth status --json` |
| OpenCode | `opencode` CLI | `opencode auth list` |
| Reasonix | `reasonix` CLI | `reasonix doctor --json` |

## Claude: Native Background Path

Agent Relay MCP uses Claude's native `claude --bg` (noninteractive) subscription path. This uses your ordinary Claude plan — no separate API billing.

- `claude -p` (print/SDK mode) is **disabled** — it uses separate Agent SDK metered billing
- `job_send` (interactive send) is **not available** for Claude bg jobs today
- Profile `claude` maps to the noninteractive `claude_bg` backend
- Readiness is validated via `claude auth status --json` before job creation

## Timeouts

| Layer | Default | Notes |
|-------|---------|-------|
| External MCP read timeout | Client-dependent | Set in your MCP client. A client-side timeout does **not** cancel the durable background job — it continues executing and results remain available via `job_tail`/`job_result`. |
| Internal preflight probe | 15s per provider | Independent bounded probe per provider, cached for 60s. A preflight failure blocks job creation — no job is started. |
| `max_runtime_sec` (agent_start) | 1800s (30 min) | Server-side job deadline, configurable per job. When exceeded, the job terminates with a terminal `timeout` result. |
| `job_tail` / `job_result` | — | Available any time after the initial `agent_start` response. No deadline is enforced on result polling. |

The `doctor` CLI reports readiness and preflight failures only. It does **not** report active job deadlines or running-job state.

## Local State and Retention

- **State directory**: `~/.local/state/agent-relay-mcp` (override with `AGENT_RELAY_STATE_DIR`)
- **Job storage**: one directory per job under `jobs/`
- **Retention**: no automatic cleanup in v0.1.3 — jobs persist until manually deleted
- **No remote telemetry**: Agent Relay MCP does not phone home. All state is local.

## Troubleshooting by Error Code

| Error Code | Meaning | Action |
|-----------|---------|--------|
| `codex_missing` | Codex CLI not on PATH | Install the Codex CLI |
| `codex_not_authenticated` | Not logged into Codex | Run `codex login` |
| `pnpm_missing` | pnpm not installed | Install pnpm (https://pnpm.io/installation) |
| `claude_missing` | Claude CLI not on PATH | Install Claude Code |
| `not_authenticated` | Claude not logged in | Run `claude auth login` |
| `opencode_missing` | OpenCode CLI not on PATH | Install the OpenCode CLI |
| `reasonix_missing` | Reasonix CLI not on PATH | Install the Reasonix CLI |
| `unsupported_os` | Provider requires different OS | Use a supported OS or different provider |
| `chatgpt_pro_manual_gate` | ChatGPT Pro needs manual setup | Launch ChatGPT desktop app and sign in |
| `acp_launch_error` | ACP agent process failed to launch (binary missing, dependency error) | Check provider CLI installation, run `agent-relay-mcp doctor` |
| `acp_protocol_error` | ACP protocol handshake or message error (version mismatch, invalid request) | Check provider and protocol logs; provider CLI may need upgrade |
| `acp_timeout` | ACP job exceeded `max_runtime_sec` while awaiting an already-delivered prompt's response | Retry with a higher `max_runtime_sec` value |
| `acp_prompt_delivery_timeout` | ACP job exceeded `max_runtime_sec` before the prompt was ever dispatched to the agent (stuck in handshake/session setup) | Check the provider CLI installation and launch, then retry |
| `preflight` | Job blocked before creation | Run `agent-relay-mcp doctor` for details |

Stable error codes are guaranteed across patch versions. The `next_action` field in job results provides exact remediation.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_RELAY_STATE_DIR` | `~/.local/state/agent-relay-mcp` | State root directory |
| `AGENT_RELAY_CLIENT_NAME` | `agent-relay-mcp` | Client name in telemetry |
| `AGENT_RELAY_CLIENT_VERSION` | — | Optional client version |
| `AGENT_RELAY_DEFAULT_CWD` | `PWD` | Default working directory for dev jobs |

**Migration note**: The old `AGENT_HARNESS_*` env var names still work but emit a `FutureWarning`. Rename them to `AGENT_RELAY_*`. The compat shim will be removed in v0.4.0.

## Architecture

```
MCP Client (Codex / Claude / OpenCode)
        │
        ▼
  FastMCP("agents")  ← 8-tool MCP surface
        │
   ┌────┼────┐
   ▼    ▼    ▼
  Codex Claude OpenCode  ← provider adapters
   │    │     │
   ▼    ▼     ▼
  tmux / print / ACP  ← transports
```

One Python package (`agent-relay-mcp` on PyPI). Bounded provider adapters under `agent_relay_mcp.adapters`. No separate plugin packages in v0.1.3.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Quick rules for contributors in [AGENTS.md](AGENTS.md).

## License

MIT — see [LICENSE](LICENSE).
