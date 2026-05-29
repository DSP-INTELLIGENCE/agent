# Codex Lane

Codex CLI is an external coding worker for this repository.

The agent delegates coding work to Codex by constructing commands and prompts, not by bypassing policy or shelling out from chat. Codex can help draft or update code, but the patch runner remains the final gate for repository changes.

## Current Scope

This lane starts with command construction only:

- `/codex status` builds a local Codex availability check
- `/codex prompt <task>` builds a Codex command list but does not run it
- `/codex package <task>` builds a Codex prompt that asks for a patch ZIP workflow

## Policy Boundaries

- Keep final deliverables as patch ZIPs
- Use `scripts/make_patch_package.py` to build patch ZIPs from real git diff output
- Use `scripts/agent_patch_runner.py` to validate and apply patch ZIPs
- Do not directly commit unvalidated edits
- Do not auto-commit or auto-push
- Future `/codex` execution must be explicit and policy-gated

## Prompt Contract

When asking Codex to package work, the prompt should tell it to:

- read `AGENTS.md`
- read `docs/project-memory.md`
- read `docs/codex-handoff.md`
- use `scripts/make_patch_package.py`
- use `scripts/agent_patch_runner.py`
- produce a patch ZIP
- avoid direct commits of unvalidated edits

## Next Step

After this command-building slice is stable, the agent can add an explicit `/codex` execution path that still routes through policy and the patch runner.
