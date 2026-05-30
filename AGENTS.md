# AGENTS.md

Guidance for coding agents working in this repository.

## Project summary

Agent is a local, AI-native terminal runtime built around explicit slash-command front doors, deterministic policy gates, typed packets, and reviewable patch packages.

## Read first

Before making changes, inspect these files:

1. `README.md`
2. `docs/README.md`
3. `docs/project-memory.md`
4. `docs/ROADMAP_PLAN.md`
5. `docs/PATCH_WORKFLOW.md`
6. `docs/CODEX_PROMPTS.md`
7. `docs/CHATGPT_HANDOFF_PROMPT.md`

## Non-negotiable boundaries

- `agent-cli.py` is the canonical terminal/batch front door.
- `agent.py` is legacy unless the task explicitly scopes work there.
- No hidden autonomy: inspect, plan, dry-run, approve, apply, report, commit, and push are distinct stages.
- No direct arbitrary shell execution from chat.
- No file mutation unless the task is a repo-change task and the result is delivered as a reviewable patch.
- No commit or push unless explicitly requested.
- No secrets, API keys, private tokens, or credentials in docs, memory, tests, patches, or reports.
- Semantic routing, AgentSpec, AgentScript, encoder, decoder, registry, render, and dispatch-preview layers are non-executing unless a later approved milestone wires them through policy gates.
- LLMs may propose or synthesize within an approved lane; they may not serve as routers, evidence sources, policy authority, or patch validators.

## Current architecture rules

Use this mental model:

```text
instruction
-> explicit slash front door or typed decode
-> registry / capability validation
-> deterministic handler
-> evidence, report, or patch package
-> optional LLM synthesis only when allowed
-> reviewable artifact
```

The target LLM lanes are:

```text
/prompt          direct base LLM lane
/ground          grounded/RAG evidence lane
/summon          persona/session control
/summon prompt   explicit persona-routed prompt
```

Do not revive legacy answer-like command names without registry metadata, tests, and roadmap approval.

## Repo-change workflow

For code or docs changes, prefer patch workflow:

```bash
git status --short
git diff
git diff --stat
# edit files
# run relevant tests
# package diff or provide a git-applyable patch
git apply --check <patch>
git apply <patch>
```

When creating a patch ZIP, include:

```text
<patch-name>.patch
changed-files.txt
README.md
apply_patch.sh
stages/00_inspect.sh
stages/01_preflight.sh
stages/02_apply.sh
stages/03_test.sh
stages/04_report.sh
stages/05_commit.sh
stages/06_push.sh
```

Run one stage at a time and stop after reporting exact output.

## Useful local commands

```bash
git status --short
git diff
git diff --stat
./scripts/agent_python.sh -m py_compile core/patch_frontdoor.py
./scripts/agent_python.sh -m py_compile core/batch_runner.py
./agent-cli.py run --text "/patch status" --format json
./agent-cli.py run --text "/codex status"
./agent-cli.py run --text "/ground reports"
python -m agentspec validate examples/agentspec/task.json
python -m agentspec dispatch examples/agentspec/task.json --dry-run
```

If a command is unavailable in the current checkout, report that exactly and use the nearest read-only inspection command.

## Codex behavior

Codex is an external coding worker. It may inspect, draft, modify a worktree, run tests, and package a patch when asked. It must not bypass the patch runner, commit, push, or manually apply patches unless the requested stage explicitly authorizes that behavior.

Use short Codex prompts by default. Use larger handoff prompts only for risky architecture changes, repository recovery, or long-context cleanup.

## Memory policy

`docs/project-memory.md` is durable repo-local memory. Update it only with stable project facts, accepted decisions, current handoff state, and checked/unchecked milestones. Keep temporary chat context out of it.

<!-- agent-architecture-lanes-adapters-endpoints-v1:start -->
## Agent architecture notes

Treat Agent as the runtime contract for lanes/routes, adapters/filters, and endpoints/decoders.

Semantic Controllers are external. They may use semantic-router, sentence transformers, embeddings, or classifiers, but Agent should not need their implementation details.

`codec.py` is the clean frontend. `codec-patch.py` is the staged patch operator. `agent.py` and `agent-cli.py` are legacy surfaces.
<!-- agent-architecture-lanes-adapters-endpoints-v1:end -->
