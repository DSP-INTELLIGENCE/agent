# Agent

Agent is an AI-native terminal runtime for explicit, reviewable local-agent work. It is built around slash-command front doors, typed runtime packets, deterministic policy gates, and patch packages.

## Architecture law

```text
No hidden autonomy.
No implicit LLM fallback.
No repo mutation outside a reviewed patch workflow.
```

A request should move through explicit boundaries:

```text
instruction
-> explicit slash front door or typed input decode
-> registry / capability validation
-> deterministic runtime handler
-> evidence, report, or patch package
-> optional LLM synthesis only when the lane permits it
-> reviewable artifact
```

## Current execution boundary

`codec.py` is the canonical operator/frontend surface. `codec-patch.py` is the staged patch operator. `agent-cli.py` remains a backend/runtime boundary and legacy CLI compatibility surface. `agent.py` remains legacy terminal compatibility.

Semantic routing, encoder layers, AgentSpec, and AgentScript are contract or frontend layers only until a later approved integration stage. They may inspect, render, validate, decode, route-preview, or build packets. They must not execute, fetch, search, mutate files, call tools, call an LLM, commit, or push.

## Active surfaces

| Surface | Purpose | Default posture |
| --- | --- | --- |
| `/patch` | Inspect, dry-run, apply, and report patch ZIP workflows through the patch runner. | Policy-gated; no auto-push. |
| `/codex` | Build Codex CLI prompts and package instructions. | Inspect-only until explicit execution milestone. |
| `/llm` | Inspect/apply local LLM presets. | Config-only; no model downloads or restarts. |
| `/web` and `/search` | Bounded fetch, extract, and search front doors. | Inspect-only; no crawl/browser/JS. |
| `/ground` | Repo-scoped deterministic evidence blocks and saved reports. | Evidence/report only; no hidden synthesis. |
| `/read`, `/ls`, `/tree`, `/find` | Repo-local inspection. | Read-only. |
| AgentSpec | Validate, decode, route, render, and dispatch-preview specs. | Non-executing. |

## LLM lanes

The target user-facing LLM lanes are intentionally narrow:

```text
/prompt          direct base LLM lane; no implicit grounding or persona routing
/ground          grounded/RAG evidence lane with final synthesis only from evidence
/summon          persona/session control
/summon prompt   explicit prompt to active summoned persona state
```

Old answer-like prompt-template command names are legacy unless reintroduced through an explicit registry entry and tests.

## Patch workflow

Patch ZIPs are the canonical repo mutation format. A valid package should be reviewable before it mutates the repo and should preserve staged additions, modifications, and deletions through apply, test, report, commit, and optional push.

Minimum portable package shape:

```text
<name>.patch
changed-files.txt
README.md
apply_patch.sh
stages/
  00_inspect.sh
  01_preflight.sh
  02_apply.sh
  03_test.sh
  04_report.sh
  05_commit.sh
  06_push.sh
```

Stage discipline:

```text
inspect -> preflight -> apply -> test -> report -> commit -> push
```

Run exactly one stage at a time, paste exact output, and stop. Commit and push require explicit operator approval.

## Codex CLI integration model

Codex is an external coding worker, not a policy bypass. Use Codex to inspect, draft, test, and package work. Bring changes back through the patch package and patch runner.

Recommended Codex prompt flow:

1. Read `AGENTS.md`, `docs/project-memory.md`, `docs/CODEX_PROMPTS.md`, and `docs/CHATGPT_HANDOFF_PROMPT.md`.
2. Inspect the repo and produce a plan.
3. Make changes in a branch or worktree.
4. Run tests.
5. Build a patch ZIP with a real git diff.
6. Do not commit or push unless the requested stage explicitly asks for it.

## Memory and roadmap

Use `docs/project-memory.md` for durable repo-local state. Do not store secrets, private credentials, API keys, tokens, or temporary chat context there.

Use `docs/ROADMAP_PLAN.md` for checked and unchecked milestones. Historical notes should be archived or linked from the active docs instead of competing with the current architecture.

## Start here

For human operators, read:

1. `docs/README.md`
2. `docs/DOCS_AUDIT.md`
3. `docs/ROADMAP_PLAN.md`
4. `docs/PATCH_WORKFLOW.md`
5. `docs/CODEX_PROMPTS.md`
6. `docs/CHATGPT_HANDOFF_PROMPT.md`

For coding agents, read `AGENTS.md` first.

<!-- agent-architecture-lanes-adapters-endpoints-v1:start -->
## Agent architecture contract

Agent is organized around:

1. Lanes / Routes
2. Filters / Adapters
3. Endpoints / Decoders

Semantic Controllers may connect natural-language intent to lanes, but they are defined outside Agent. Agent owns the lane/adapters/endpoints execution contract.

See:

- `docs/ARCHITECTURE.md`
- `docs/LANES.md`
- `docs/ADAPTERS.md`
- `docs/ENDPOINTS.md`
- `docs/SEMANTIC_CONTROLLERS.md`
- `docs/CODEC_FRONTEND.md`
<!-- agent-architecture-lanes-adapters-endpoints-v1:end -->
