# Handoff

This file captures the current repo memory for continuing Agent work.

## Current state

- Current branch used for recovery: `research/route-execute-live-wiring`.
- The unsafe dirty live route-execute experiment was removed before the pivot.
- The roadmap now pivots toward `agent-cli.py` as backend and semantic/encoder layers as frontend-only.
- Focused recovery tests passed before the pivot docs commit:
  - runtime/router focused tests: `47 passed`
  - semantic route / LaneInvocation / AgentScript tests: `259 passed`

## Architecture direction

```text
encoder / semantic-router frontend
-> explicit agent-cli.py backend command or packet request
-> structured backend result packet
-> decoder/final response over validated packet evidence
```

Rules to preserve:

- No lane, no LLM.
- No spec, no execution.
- No packet, no final factual claim.
- Semantic router proposes and diagnoses only; it does not execute.
- `RouteDecision` is inspect-only.
- `agent-cli.py` is the backend execution boundary.
- Backend execution must enter through explicit CLI commands or approved AgentScript runner paths.
- Decoder/final response must not invent tool results.

## Paused work

Do not resume live route execution wiring as previously attempted. In particular:

- do not route plain text fallback into semantic route execution
- do not invoke `AgentCore`/Ollama from route parity or route preview paths
- do not make `RouteDecision` authorize execution
- do not connect semantic routing directly to live terminal execution

## Next safe implementation candidates

- `agent-cli.py` structured backend packet output
- encoder-to-agent-cli request schema
- AgentScript validation gap
- LaneInvocation compiler test
- route diagnostics cleanup
- patch runner verification

## Operator model

ChatGPT designs architecture and creates staged patch ZIPs.

Codex or another repo operator only runs a requested stage script and reports
exact output unless explicitly told otherwise. It should not manually edit files,
create patches, or commit/push outside the staged workflow.

<!-- agent-three-llm-lanes:start -->
## Current LLM lane contract

```text
/prompt  -> direct base LLM
/ground  -> grounded/RAG evidence builder plus final LLM answer
/summon  -> persona/session control; /summon prompt is explicit persona-routed prompt
```

Everything else that looked like an answer lane is legacy and unwired. Do not add aliases. Do not design provider or RAG work around legacy prompt-template surfaces.

Next implementation milestone after stabilizing `/ground`: provider adapter layer and a stable EvidencePacket schema.
<!-- agent-three-llm-lanes:end -->

<!-- agent-grounded-resolver-memory:start -->
## Grounded resolver handoff

Current user-facing model:

```text
/prompt        direct base LLM
/ground        primary grounded/RAG evidence path
/summon        persona/session control
/summon prompt explicit persona-routed prompt
```

Checked:

- [x] lane model simplified around `/prompt`, `/ground`, and `/summon`
- [x] old answer-like command names are unwired rather than aliased
- [x] `/summon prompt` added as the explicit summon/persona prompt route
- [x] first `/ground` resolver repair covers normalization, entity-title gating, and short ambiguous location requests

Unchecked:

- [ ] define a stable EvidencePacket / grounding result schema
- [ ] make `/ground` always produce that packet before rendering diagnostics or answers
- [ ] preserve `/prompt` as a direct LLM path
- [ ] add real grounding providers only through adapters and optional dependency groups
- [ ] update lane health audit once grounded packet checks are deterministic and non-live
<!-- agent-grounded-resolver-memory:end -->

<!-- agent-legacy-semantic-stack:start -->
## Legacy semantic stack handoff

The semantic router, AgentSpec, AgentScript, and encoder layers are now legacy/unwired. They should remain out of the runtime path and should not be repaired as product surfaces.

Current active LLM lanes stay `/prompt`, `/ground`, and `/summon` only. `/ground` owns future RAG/grounding provider work.
<!-- agent-legacy-semantic-stack:end -->
