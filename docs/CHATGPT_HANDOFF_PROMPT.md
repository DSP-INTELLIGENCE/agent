# ChatGPT Handoff Prompt

Use this prompt when starting a fresh ChatGPT session or handing the repo to another assistant.

```text
You are continuing work on https://github.com/DSP-INTELLIGENCE/agent.

First read these files in order:
1. AGENTS.md
2. README.md
3. docs/README.md
4. docs/project-memory.md
5. docs/DOCS_AUDIT.md
6. docs/ROADMAP_PLAN.md
7. docs/PATCH_WORKFLOW.md
8. docs/CODEX_PROMPTS.md

Current architecture rules:
- agent-cli.py is the canonical terminal/batch backend boundary.
- agent.py is legacy unless the task explicitly scopes it.
- Slash roots are explicit command surfaces.
- No hidden autonomy: inspect, plan, dry-run, approve, apply, report, commit, and push are distinct stages.
- Semantic routing, encoder/decoder, AgentSpec, AgentScript, registry rendering, and dispatch preview are non-executing unless a later approved milestone wires them through policy gates.
- LLMs may propose or synthesize only inside approved lanes; they may not be routers, evidence sources, policy authorities, or patch validators.
- Repo changes must be delivered as a reviewable git patch or patch ZIP.
- Do not commit or push unless explicitly requested.

Current patch package expectation:
- Include a .patch file, changed-files.txt, README.md, apply_patch.sh, and staged scripts when possible.
- Validate with git apply --check before applying.
- Run one stage at a time and stop after reporting exact output.

Current Codex integration model:
- Codex CLI is an external coding worker.
- Codex may inspect, draft, test, and package work.
- Codex must not bypass the patch runner, commit, or push unless explicitly requested.

Your first response should:
1. Briefly summarize the repo state from the docs.
2. Identify any stale or conflicting instructions before editing.
3. Propose a patch plan with files changed and tests.
4. Use patch diff workflow for repo changes.
```

## Handoff checklist

Before ending a session, record:

- What changed.
- Files changed.
- Tests run and exact outcomes.
- Checked milestones completed.
- Unchecked milestones remaining.
- Any known risks.
- Whether a patch ZIP, branch, commit, or PR exists.
- Next recommended command.

## Minimal status block

```text
Status:
- Branch:
- Last commit:
- Working tree:
- Patch package:
- Tests:
- Checked:
- Unchecked:
- Next step:
```
