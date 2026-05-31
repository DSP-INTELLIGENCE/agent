# Documentation Audit

Audit date: 2026-05-29

## Summary

The repository already has the right ingredients for a safe agent workflow: explicit slash roots, `codec.py` as the operator/frontend surface, `codec-patch.py` as the staged patch operator, patch ZIPs, repo-local memory, Codex prompt construction, and deterministic/non-executing AgentSpec scaffolding.

The cleanup problem is that these ideas are spread across many files with different generations of terminology. This makes new agents likely to revive old lane names, treat semantic routing as execution authority, or skip patch-stage discipline.

## Findings

### 1. Root docs are too compressed

`README.md`, `AGENTS.md`, and several docs are effectively single-line Markdown blocks. That makes them hard for humans to review and hard for agents to quote, patch, and maintain.

Cleanup: rewrite root docs as normal Markdown with stable headings and explicit links.

### 2. Lane names conflict across generations

Older docs still mention `/question`, `/web`, `/scrape`, prompt-template lanes, plugin/tool abstractions, and semantic route execution. Newer docs point to `/prompt`, `/ground`, `/summon`, `/patch`, `/codex`, `/llm`, typed runtime decoding, and explicit `agent-cli.py` backend boundaries.

Cleanup: make current lanes explicit in root docs and mark old answer-like/template names as legacy until reintroduced by tests and registry metadata.

### 3. Patch workflow is central but scattered

Patch rules appear across root README notes, `docs/project-memory.md`, `docs/roadmap.md`, `docs/patch-frontdoor.md`, `docs/patch-package-builder.md`, and `docs/patch-runner.md`.

Cleanup: add `docs/PATCH_WORKFLOW.md` as the canonical operator contract, then link supporting implementation docs from there.

### 4. Codex role needs a sharper contract

The existing docs correctly describe Codex as an external worker and inspect-only lane, but prompts and operational modes are scattered between `docs/codex-lane.md`, `docs/codex-handoff.md`, and memory notes.

Cleanup: add `docs/CODEX_PROMPTS.md` with reusable short prompts and long prompts for patch packaging, docs cleanup, review, and stage running.

### 5. Handoff needs a reusable front door

There is a Codex handoff file, but a ChatGPT-facing continuation prompt should be a separate reusable artifact so a new assistant can reconstruct state without reading every historical note first.

Cleanup: add `docs/CHATGPT_HANDOFF_PROMPT.md`.

### 6. Roadmap and memory overlap

`docs/project-memory.md` contains detailed current state, known commands, and implementation facts. `docs/roadmap.md` mixes current roadmap, historical phases, and milestone memories.

Cleanup: preserve `project-memory.md` as durable facts and add `docs/ROADMAP_PLAN.md` as the concise checked/unchecked active plan.

## Canonical doc roles after cleanup

| File | Role |
| --- | --- |
| `README.md` | Human-facing overview and current architecture. |
| `AGENTS.md` | Agent-facing operating rules. |
| `docs/README.md` | Documentation map. |
| `docs/project-memory.md` | Durable facts and accepted state. |
| `docs/DOCS_AUDIT.md` | Cleanup findings and rationale. |
| `docs/ROADMAP_PLAN.md` | Checked/unchecked milestones. |
| `docs/PATCH_WORKFLOW.md` | Patch ZIP and staged operator contract. |
| `docs/CODEX_PROMPTS.md` | Codex CLI prompts. |
| `docs/CHATGPT_HANDOFF_PROMPT.md` | ChatGPT continuation prompt. |

## Suggested next cleanup pass

1. Archive or label historical docs that contradict current lane rules.
2. Normalize all Markdown files from single-line form into reviewable headings and lists.
3. Replace stale `/question` language with the accepted `/ground` path or mark it legacy.
4. Make `docs/roadmap.md` link to `docs/ROADMAP_PLAN.md` instead of duplicating status.
5. Add a docs smoke test that checks for forbidden current-architecture terms in active docs unless they appear under a `Legacy` heading.
