# Roadmap

## North Star

Agent is a lane-based terminal/runtime system with explicit, auditable pathways to LLMs, tools, grounding, patching, and local operations.

Core rule:

```text
No lane, no LLM.
```

## Phase 0 — Stabilize docs and workflow

- Audit docs for stale active-lane claims.
- Fix `codec ground -> /ground`.
- Fix codec-patch report so it includes untracked files.
- Confirm patcher workflow is reliable.

## Phase 1 — Codec frontend

- `codec.py prompt` delegates to `/prompt`.
- `codec.py ground` delegates to `/ground`.
- `codec.py patch` delegates to the canonical patch engine.
- `codec.py status` reports active lanes and patch engine availability.

## Phase 2 — Patcher integration

- `codec-patch.py` is the trusted package operator.
- `agent-cli.py install patch` delegates to the same engine.
- No second patch engine.
- Report stage shows tracked and untracked changed files.

## Phase 3 — Ground EvidencePacket bridge

- Bridge live `/ground` to EvidencePacket on a fresh temp branch.
- Store `registry["last_evidence_packet"]`.
- Use `packet.render_answer_context()` for grounded synthesis.
- `/grounding` and `/sources` become packet-first.
- Preserve legacy fallback for display only.
- No raw prompt fallback.

## Phase 4 — Provider adapters

- Add dependency-free provider interface first.
- Optional packages later: Wikipedia, fetch/extract, web search, repo docs, local docs, vector store.
- No API-key dependency by default.

## Phase 5 — Tools and shell integration

- Tools are explicit, typed, policy-gated capabilities.
- Shell is deny-by-default and read-only by default.
- Mutating operations require approval and audit artifacts.
- LLM plans; dispatcher executes only approved structured actions.

## Phase 6 — Evaluation and reliability

- Golden tests for EvidencePacket.
- Grounded answer regression set.
- Patcher package self-tests.
- Tool policy tests.
- Docs consistency tests.
