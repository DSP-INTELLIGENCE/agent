# Codex Prompts

Use short prompts by default. Use the long handoff only for risky architecture work, cleanup across many docs, or recovery after context loss.

## Ground rules for every Codex prompt

Tell Codex:

- Read `AGENTS.md` first.
- Treat `codec.py` as the canonical operator/frontend surface and `codec-patch.py` as the staged patch operator.
- Treat `agent.py` as legacy unless the task explicitly scopes it.
- Do not commit or push unless explicitly asked.
- Deliver repo changes as a patch ZIP or a git-applyable patch.
- Run `git status --short`, `git diff`, and `git diff --stat`.
- Run relevant tests and report exact output.
- Keep patch workflow stages separate: inspect, preflight, apply, test, report, commit, push.

## Prompt: repo audit only

```text
Read AGENTS.md, README.md, docs/README.md, docs/project-memory.md, and docs/ROADMAP_PLAN.md.

Audit the repository for contradictions, stale lane names, hidden execution paths, and docs that conflict with the current patch workflow.

Do not edit files. Do not commit. Do not push.

Return:
1. Findings by file.
2. Risk level for each finding.
3. Proposed patch plan.
4. Tests you would run.
```

## Prompt: implement a patch ZIP

```text
Read AGENTS.md, README.md, docs/project-memory.md, docs/PATCH_WORKFLOW.md, and docs/CODEX_PROMPTS.md.

Implement this task as a reviewable patch package:

TASK:
<describe the change>

Rules:
- Use a clean branch or worktree.
- Inspect with git status --short before edits.
- Make minimal changes.
- Run relevant tests.
- Build a patch ZIP containing change.patch, changed-files.txt, README.md, apply_patch.sh, and staged scripts if available.
- Do not commit or push.

Return the package path, changed files, test output, and any risks.
```

## Prompt: run one stage only

```text
Read AGENTS.md and docs/PATCH_WORKFLOW.md.

Run exactly this patch stage and stop:

STAGE:
<00_inspect | 01_preflight | 02_apply | 03_test | 04_report | 05_commit | 06_push>

PACKAGE:
<path to zip or patch>

Rules:
- Run only the requested stage.
- Paste exact command output.
- Do not continue to the next stage.
- Do not commit or push unless the requested stage is commit or push.
```

## Prompt: package docs cleanup

```text
Read AGENTS.md, README.md, docs/README.md, docs/project-memory.md, docs/DOCS_AUDIT.md, and docs/PATCH_WORKFLOW.md.

Clean documentation only. Do not change runtime code.

Goals:
- Keep root README human-facing.
- Keep AGENTS.md agent-facing and concise.
- Keep project-memory.md as durable factual memory.
- Keep roadmap state in docs/ROADMAP_PLAN.md.
- Move historical or contradictory material under clear Legacy headings or archive links.
- Preserve the current architecture: agent-cli.py boundary, explicit slash front doors, non-executing semantic/AgentSpec layers, patch ZIP workflow.

Deliver as a patch ZIP. Do not commit or push.
```

## Prompt: review patch package

```text
Review this patch package without applying it:

PACKAGE:
<path>

Read AGENTS.md and docs/PATCH_WORKFLOW.md first.

Run inspection and preflight only. Report:
1. Package structure.
2. Changed files.
3. Patch stat.
4. Whether git apply --check passes.
5. Any risky paths or workflow violations.

Do not apply. Do not commit. Do not push.
```

## Prompt: update project memory after accepted change

```text
Read docs/project-memory.md and the accepted diff.

Update project memory only with stable facts from the accepted change.

Do not store secrets, credentials, tokens, or temporary chat context.

Use checked/unchecked bullets where helpful.

Deliver as a patch. Do not commit or push.
```
