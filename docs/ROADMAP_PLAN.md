# Roadmap Plan

This is the concise active roadmap. Use `docs/project-memory.md` for durable factual state and implementation history.

## Current thesis

Build a minimal local agent core where slash roots are explicit command surfaces, `codec.py` is the operator/frontend surface, `codec-patch.py` is the staged patch operator, deterministic policy gates run before risky behavior, and repository mutation flows through patch packages.

## Checked milestones

- [x] Establish `codec.py` as the canonical operator/frontend surface and `codec-patch.py` as the staged patch operator.
- [x] Treat `agent.py` as legacy unless explicitly scoped.
- [x] Keep patch ZIPs as the canonical repo mutation workflow.
- [x] Add patch runner and package-builder docs.
- [x] Keep Codex lane inspect-only until an explicit execution milestone.
- [x] Record durable state in `docs/project-memory.md`.
- [x] Keep AgentSpec schema/render/decode/route/dispatch-preview non-executing.
- [x] Keep repo-local `/read`, `/ls`, `/tree`, `/find`, and `/search repo` bounded and deterministic.
- [x] Keep `/web` bounded to fetch/extract/search without crawl/browser/JS execution.
- [x] Keep `/ground` repo/report surfaces inspect-only and evidence-oriented.

## Unchecked milestones

- [ ] Normalize active docs into readable Markdown and archive or label historical contradictions.
- [ ] Add docs smoke tests for stale active-lane language and hidden-autonomy language.
- [ ] Add a stable EvidencePacket pipeline for `/ground` answer synthesis.
- [ ] Wire response policy into live answer paths without hidden autonomy.
- [ ] Replace direct chat fallback points with typed runtime input and explicit lane behavior.
- [ ] Add Codex CLI execution only after policy, model defaults, and patch-stage approval are explicit.
- [ ] Add project-memory maintenance command or documented update workflow.
- [ ] Add patch package verification for staged scripts and manifest completeness.
- [ ] Make roadmap updates flow through checked/unchecked milestones instead of long narrative notes.

## Phase plan

### Phase 1 — Documentation front door

- Root `README.md` explains active architecture and surfaces.
- Root `AGENTS.md` gives concise agent operating rules.
- `docs/README.md` maps active docs.
- `docs/DOCS_AUDIT.md` captures cleanup findings.
- `docs/ROADMAP_PLAN.md` owns active milestones.

### Phase 2 — Patch workflow hardening

- Keep patch ZIP package shape deterministic.
- Keep staged scripts one-command, one-stage, stop-after-output.
- Validate `changed-files.txt` against patch content.
- Validate new docs/tests/source files are packaged and staged explicitly.

### Phase 3 — Codex CLI integration

- Keep `/codex` command construction inspect-only by default.
- Add explicit Codex execution only after policy gates are documented and tested.
- Require Codex-generated changes to return through patch ZIPs.
- Add prompts for audit, implementation, package review, and one-stage execution.

### Phase 4 — Runtime boundary cleanup

- Replace hidden fallback points with typed input specs and visible route decisions.
- Keep semantic routing as candidate generation only.
- Keep AgentSpec and AgentScript non-executing until an approved runner contract exists.

### Phase 5 — Grounding and response policy

- Define `GroundingQuery -> EvidencePacket -> render/synthesize`.
- Make `/ground` diagnostics and answer synthesis read from the same packet.
- Add provider adapters behind graceful fallback.
- Add groundedness evals only after packet output is stable.

## Rule for roadmap edits

Use checked/unchecked bullets. Keep historical detail in `docs/project-memory.md` or archive docs. Do not let roadmap narrative override the current architecture boundaries.
