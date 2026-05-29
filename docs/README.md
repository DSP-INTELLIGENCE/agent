# Documentation Index

This is the active documentation map for `agent`. Keep this index short and use links instead of duplicating architecture notes.

## Read first

1. `../README.md` — project overview, active surfaces, and patch workflow.
2. `DOCS_AUDIT.md` — current documentation audit and cleanup findings.
3. `ROADMAP_PLAN.md` — checked/unchecked milestones and phased plan.
4. `PATCH_WORKFLOW.md` — staged patch ZIP contract and operator flow.
5. `project-memory.md` — durable repo-local state and handoff memory.
6. `CODEX_PROMPTS.md` — short and long prompts for Codex CLI work.
7. `CHATGPT_HANDOFF_PROMPT.md` — reusable ChatGPT-to-agent handoff prompt.

## Active architecture references

- `architecture.md` — active system architecture.
- `runtime-boundaries.md` — hard separation rules.
- `runtime-pipeline.md` — current live prompt flow and fallback risk map.
- `runtime-router-redesign.md` — typed runtime input target design.
- `runtime-router-audit-roadmap.md` — router migration phases.
- `command-registry-audit.md` — command/plugin/tool surface inventory.
- `data-agent-retirement-plan.md` — path away from legacy `data_agent/`.
- `agentspec-roadmap.md` — AgentSpec contract boundary.

## Active operator references

- `cli-usage.md` — command examples.
- `patch-frontdoor.md` — `/patch` front-door notes.
- `patch-package-builder.md` — patch ZIP builder notes.
- `patch-runner.md` — patch runner gates.
- `codex-lane.md` — Codex lane boundaries.
- `codex-handoff.md` — long-form Codex continuation state.
- `llm-control-plane.md` — LLM front-door policy.
- `web-lane.md` — web/search/fetch boundaries.

## Documentation policy

- Keep root `README.md` human-facing.
- Keep root `AGENTS.md` agent-facing and concise.
- Keep durable state in `project-memory.md`.
- Keep operational prompts in `CODEX_PROMPTS.md` and `CHATGPT_HANDOFF_PROMPT.md`.
- Keep roadmap status in `ROADMAP_PLAN.md`.
- Archive or clearly label historical notes so they do not compete with active docs.
