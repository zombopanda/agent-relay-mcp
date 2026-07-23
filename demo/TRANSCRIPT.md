# Demo transcript

The GIF shows one Ghostty window and two real MCP calls against fixture `v1`.
Provider wording may vary slightly; the semantic answer and pass markers must
match this transcript.

1. Start Codex in the repository root.
2. Give Codex the first prompt from [`PROMPTS.md`](PROMPTS.md).
3. Codex invokes the `claude` profile through Agent Crossbar.
4. Claude reports that whitespace-only input becomes `Anonymous`.
5. Codex prints `CODEX → CLAUDE: PASS`, then exits.
6. Start Claude in the same Ghostty window.
7. Give Claude the second prompt from [`PROMPTS.md`](PROMPTS.md).
8. Claude invokes the `codex` profile through Agent Crossbar.
9. Codex reports that whitespace-only input becomes `Anonymous`.
10. Claude prints `CLAUDE → CODEX: PASS`.

No provider output is simulated. Only idle waiting may be accelerated.
