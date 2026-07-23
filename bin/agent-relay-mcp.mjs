#!/usr/bin/env node

/**
 * Agent Relay MCP — npm launcher for the Python CLI.
 *
 * This is a logic-free wrapper: it delegates entirely to the canonical
 * Python distribution (`agent-relay-mcp` on PyPI, installed via uv).
 * The npm package contains no orchestration logic.
 *
 * Prerequisites: uv (https://docs.astral.sh/uv/getting-started/installation/)
 */

import { spawn } from "node:child_process";

const args = ["agent-relay-mcp", ...process.argv.slice(2)];

// Try `uvx` first (standalone, no local install needed), then fall
// back to `uv tool run` for users who prefer pinned installs.
const child = spawn("uvx", args, { stdio: "inherit" });

child.on("error", () => {
  // uvx not on PATH — try uv tool run as fallback
  const fallback = spawn("uv", ["tool", "run", ...args], { stdio: "inherit" });
  fallback.on("error", () => {
    console.error("agent-relay-mcp requires uv (https://docs.astral.sh/uv/getting-started/installation/)");
    process.exit(1);
  });
  fallback.on("exit", (code, signal) => {
    if (signal) process.kill(process.pid, signal);
    else process.exit(code ?? 1);
  });
});

child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 1);
});
