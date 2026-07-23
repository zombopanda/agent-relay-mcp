# Bidirectional demo prompts

Fixture version: `v1`

Run both prompts from the repository root. Do not edit the fixture during the
recording.

## Codex invokes Claude

```text
Use Agent Crossbar to ask the claude profile with model sonnet to inspect
demo/fixture/crossbar_demo.py. Ask Claude for one concise sentence describing what
display_name returns for whitespace-only input. Show the provider result and
finish with: CODEX → CLAUDE: PASS
```

## Claude invokes Codex

```text
Use Agent Crossbar to ask the codex profile to inspect
demo/fixture/crossbar_demo.py. Ask Codex for one concise sentence describing what
display_name returns for whitespace-only input. Poll only with `job_result`;
do not call `job_tail`. Show the provider result and finish with:
CLAUDE → CODEX: PASS
```
