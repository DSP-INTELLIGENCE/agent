# Runtime Router Audit Roadmap

This document records the current routing split and the phased plan for moving
from raw `if`/`elif` prompt routing to typed route decisions.

It is documentation only. It does not change runtime behavior.


## Current Pivot

The live route execution experiment is paused. Runtime router work must treat
semantic routing and encoder layers as frontend-only. The backend execution
boundary is `agent-cli.py`, reached by explicit commands or approved
AgentScript runner paths.

`RouteDecision` remains inspect-only. It does not authorize answering, fetching,
searching, mutation, tool use, or execution. Plain text fallback must not route
into semantic route execution.

The next execution-facing direction is a structured `agent-cli.py` backend packet
MVP, followed by an encoder-to-agent-cli request schema.

## Current Diagnosis

- The typed runtime decoder exists in `core/runtime_decoder/`.
- `decode_runtime_input(text)` emits typed `InputSpec` values and deterministic trace metadata.
- `route_runtime_input(spec)` emits inspect-only `RouteDecision` values.
- Active execution routing still lives in `core.batch_runner.run_command()`.
- `run_command()` still routes from raw text and token strings.
- `agent-cli.py` debug route metadata now comes from `decode_runtime_input(text)` plus `route_runtime_input(spec)`, while `core.batch_runner` execution routing still lives separately.
- `core.runtime_decoder.decode_runtime_input()` is not consumed by active execution yet.
- `core.response_policy` exists but is not in the live routing path.
- `agent.py` remains a separate legacy runtime with its own router stack.
- no PyPI router package is used; the runtime router is dependency-free, typed, table-driven, deterministic, inspectable, and small.
- execution parity tests now compare typed route preview against current `core.batch_runner.run_command()` behavior and record known gaps.
- `core.batch_runner` now has an internal handler registry for behavior-identical execution dispatch.
- `core.batch_runner` now uses registry-backed dispatch planning for the read-only repo surfaces `/read`, `/ls`, `/tree`, and `/find` while preserving behavior.
- the parser boundary between `runtime_decoder` whitespace tokenization and `core.batch_runner` `shlex.split()` compatibility is explicitly documented.

## Target Future Invariant

The target runtime flow is:

```text
raw input
-> decode_runtime_input(text)
-> InputSpec
-> route_runtime_input(spec)
-> RouteDecision
-> future policy/grounding gates as required
-> future handler dispatch
-> structured artifact/result
```

`RouteDecision` values are typed route descriptions. They are not permission to
answer, execute, fetch, search, ground, mutate, or call tools.

## Phase 1: Inspect-Only Route Decisions

Milestone:

```text
Add runtime route decision model and inspect-only route helper.
```

Add:

- `core/runtime_decoder/router.py`
- `RouteDecision`
- `route_runtime_input(spec)`

Rules:

- diagnostic only
- route modes are preview modes, not execution modes
- no execution
- no handler calls
- no `run_command()` behavior changes
- no `agent-cli.py` behavior changes yet

## Phase 2: Replace Debug Route Duplication

Plan:

`agent-cli.py` debug route metadata now uses the typed preview helper:

```text
decode_runtime_input(text)
-> route_runtime_input(spec)
```

Rules:

- diagnostics only
- no execution changes
- do not touch `run_command()` behavior yet

Goal:

Debug route metadata and typed route preview come from the same source.

## Phase 3: Add Parity Tests Before Execution Changes

Plan:

Add tests comparing typed route preview against current runtime behavior for
existing command families:

- `/patch`
- `/llm`
- `/codex`
- `/web`
- `/search`
- `/ground`
- `/read`
- `/ls`
- `/tree`
- `/find`
- `/tool`
- `/switch`

Goal:

Know where typed preview and current execution routing differ before changing
runtime behavior.

Status:

- parity tests are now in place for the current command families
- `/commands` now previews as the help route in `route_runtime_input()`, closing the preview gap with command registry metadata.
- known gaps are recorded explicitly instead of being treated as failures in the audit step

## Phase 4: Introduce Batch Runner Handler Registry

Plan:

Inside `core.batch_runner`, add a table mapping route or handler names to
existing functions.

Rules:

- behavior-identical refactor
- keep `shlex.split()` compatibility for `core.batch_runner`
- no typed decoder execution integration yet

Goal:

Reduce long raw `if`/`elif` routing risk without changing behavior.

Status:

- the internal handler registry is now in place
- execution semantics remain unchanged

## Command Registry Audit

`docs/command-registry-audit.md` records the current command, plugin, and tool surface audit.

`core/command_registry.py` now provides the dependency-free command registry schema and default fixtures only; it does not call handlers or change execution behavior.

The switch matrix is intended to become a `/commands` registry surface, not a plugin/tool subsystem.
`docs/render` is the inspect-only registry docs rendering surface in the schema layer.
`core/command_registry_render.py` renders registry metadata deterministically as inspect-only JSON and markdown.
Command registry route parity tests now compare typed preview modes against registry metadata before execution integration.

This audit should be used to decide which surfaces remain, which should move into a dependency-free command registry, and which should stay legacy until parity tests settle their status.

The audit should keep parser-family boundaries explicit:

- `runtime_decoder_simple` for typed runtime preview
- `batch_runner_shlex` for current execution compatibility
- `internal_only` for metadata and diagnostics

## Phase 5: Document Parser Boundary

Document and preserve this boundary:

- `runtime_decoder` uses simple whitespace tokenization.
- `core.batch_runner` may keep `shlex.split()` for compatibility.
- these are not the same parser.
- typed runtime input should not pretend to preserve shell parsing semantics.
- typed args are diagnostic-only and must not be treated as execution args.
- future execution integration must choose explicitly between typed runtime whitespace semantics, legacy batch `shlex` semantics, or a command-specific parser.

## Phase 6: Add Policy Gate Preview For Factual Input

Plan:

When `decode_runtime_input()` returns `FactualAnswerSpec`, create an
inspect-only policy route decision.

Rules:

- no source synthesis yet
- no answer generation yet
- no automatic grounding yet
- clarify/refuse/needs-grounding decision only

Goal:

Stop treating factual natural language as plain chat in diagnostics.

## Phase 7: Make Direct Chat Fallback Explicit

Plan:

Introduce a visible route mode such as:

- `chat_direct`
- `chat_fallback_unprotected`

Goal:

Logs and tests must show when direct assistant fallback is happening.

## Phase 8: Guard Direct Fallback

Plan:

Only allow chat fallback for:

- clearly non-factual general chat
- policy-allowed text
- no slash ambiguity
- no required grounding

Everything else should clarify, refuse, or request grounding.

## Phase 9: Execution Integration

Only after parity and policy previews are stable, move toward:

```text
raw input
-> decode_runtime_input(text)
-> route_runtime_input(spec)
-> policy/grounding gates as required
-> handler registry
-> structured artifact/result
```

Goal:

Replace raw `if`/`elif` prompt routing with typed route decisions.

## Phase 10: Defer Legacy Runtime Integration

Plan:

Do not integrate `agent.py` yet.

Keep `agent-cli.py` and `core.batch_runner` as the proving ground. Later decide
whether `agent.py` should be:

- bridged
- replaced
- left legacy

## Non-Negotiable Boundaries

- AgentSpec is not executable.
- AgentScript is executable.
- `agentspec` never executes.
- `core/compiler` never executes.
- `response_policy` decides, but does not answer.
- grounding produces evidence, not guesses.
- runner executes only explicit approved AgentScript commands.
- router decides route shape; it does not execute.
- route metadata does not authorize answering.
- decode metadata does not authorize execution.
- no PyPI router package is used.
