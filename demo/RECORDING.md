# Recording the Ghostty demo

Record from a clean public snapshot with the supported Codex and Claude
profiles authenticated. Use one Ghostty window at a README-readable font size.

1. Set the working directory to the clean snapshot root.
2. Run `agent-crossbar doctor` and keep credentials and private paths outside
   the visible frame.
3. Capture only the Ghostty window. Prefer window-only trajectory screenshots
   taken after real actions; never record the main display or unrelated windows.
4. Start Codex and paste the first prompt from `PROMPTS.md`.
5. Wait for the real Claude result and the first pass marker, then exit Codex.
6. Start Claude and paste the second prompt.
7. Wait for the real Codex result and the second pass marker, then stop.
8. Assemble the real post-action frames in chronological order. Remove idle
   frames only; do not splice, replace, or synthesize commands or provider output.
9. Export `agent-crossbar-demo.gif` at 30–45 seconds and optimize it without
   changing frames containing commands or results.
10. Update `metadata.json`, confirm the transcript, and run the demo asset test.

Before committing, inspect every frame for credentials, private repository
names, usernames, home paths, notifications, and unrelated windows.
