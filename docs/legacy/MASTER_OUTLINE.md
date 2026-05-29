# Agent Master Outline

## Purpose

Build a deterministic, local-first agent runtime that can:

- route user intent
- resolve capability policy
- execute only approved tools
- use LLMs as synthesis engines, not as uncontrolled executors
- keep facts grounded in sources
- preserve safety, secrecy, and reproducibility

Primary rule:

```text
runtime controls execution
switch controls routing
LLM controls synthesis
grounding controls factual claims
```

## Core Architecture

```text
agent
├── core runtime
├── switch spine
├── tool bridge
├── llm front doors
├── provider clients
├── model catalog
├── model selection state
├── grounding layer
├── docs / roadmap
└── tests / validation
```

Control flow:

```text
user input
→ front door
→ switch spine
→ capability resolution
→ optional planning
→ optional manifest-gated execution
→ optional provider call
→ normalized result
```

## Control Plane

### `/switch`

`/switch` is the policy and capability control plane.

Owns:

- capability catalog loading
- enabled / visible / plannable / dispatchable state
- selected backend/provider hints
- required switch checks
- blocker reasons
- routing decisions

Never:

- execute providers
- execute tools directly
- invent backend choices
- become a second front door

### `/tool`

`/tool` is the manifest-gated execution bridge.

Owns:

- manifest validation
- command validation
- safe CLI execution
- explicit allowed arguments

Never:

- bypass switch policy
- hardcode tool behavior outside manifests
- act as policy control

## Front Doors

### `/llm`

`/llm` is the LLM domain front door.

Supports:

- `/llm models`
- `/llm choose`
- `/llm select`
- `/llm use`
- `/llm current`
- `/llm clear`
- `/llm chat`
- `/llm ask`
- `/llm test`

Responsibilities:

- parse user intent
- resolve through switch spine
- use provider adapters only when allowed
- maintain safe model selection state
- expose a stable response envelope

### `/ai`

`/ai` is the current alias into the LLM chat path.

Behavior:

- maps to `llm.chat`
- shares the same chat target
- shares the same policy checks
- shares the same response envelope

### Other Domains

```text
/image
/audio
/sd
```

These are domain front doors, not backend selectors.

## LLM Subsystem

### Model Listing

- live model discovery
- provider-backed list fetch
- catalog normalization
- chat-capable filtering
- no hardcoded model inventory

### Model Selection

- saved local selection
- provider + `model_id` only
- colon-preserving model parsing
- current / clear support
- optional live validation

### Chat Execution

- saved selection becomes active default
- `/llm chat`, `/llm ask`, and `/llm test` use the selected model when allowed
- fallback is safe when no selection exists
- blocked selection returns a clear error
- secrets and raw provider payloads are excluded

### Response Envelope

Current stable chat result shape includes:

- provider
- `model_id`
- mode
- status
- `response_text`
- error
- policy
- `provider_call_made`
- metadata

Backward compatibility:

```text
chat_result_error is retained for older callers
```

## Grounding Layer

Grounding is separate from LLM selection and execution.

Responsibilities:

- source-backed factual claims
- provenance discipline
- correction-aware behavior
- refusal when evidence is weak
- no invented personal details

Should block or refuse:

- phone numbers
- home addresses
- workplaces
- identity claims
- unsupported location claims
- unsupported inference from weak snippets

## Runtime State

### Safe Runtime Files

Selection state lives in a local runtime file:

```text
data_agent/runtime/llm_model_selection.json
```

Rules:

- provider and `model_id` only
- no secrets
- no prompts
- no raw provider payloads
- no API keys

### Other State

Any future runtime state should be:

- local
- explicit
- secret-safe
- schema-versioned
- easy to clear

## Provider / Adapter Layer

Provider clients are reusable helpers.

Current responsibilities:

- config diagnostics
- Open WebUI model listing
- chat execution adapters
- model catalog normalization

Rules:

- provider calls are opt-in
- normal tests stay offline by default
- adapters do not become policy control

## Planning And Docs System

Current roadmap source of truth:

```text
docs/roadmap/CURRENT_AGENT_ROADMAP.md
```

Supporting docs:

```text
docs/SWITCH_CONTROL_PLANE.md
docs/DOMAIN_FRONT_DOORS.md
docs/LLM_MODEL_SELECTION.md
docs/LLM_MODEL_LIST_LIVE.md
docs/LLM_MODEL_CATALOG.md
docs/LLM_PROVIDER_CONFIG.md
docs/LLM_FRONT_DOOR_SWITCH_RESOLVE.md
```

Older planning docs are historical unless explicitly promoted:

```text
docs/roadmap/AGENT_CODEX-ROADMAP_MASTER_PLAN.md
docs/roadmap/AGENT_ROADMAP_AND_PLANS_2026_05_19.md
docs/AGENT_TOOLS_ROADMAP.md
other phase / audit / handoff docs
```

Rule:

```text
current roadmap is the coordination point
older docs remain reference/history
append instead of overwriting when possible
```

## Current Implemented State

### Switch Plane

Implemented:

- switch spine
- capability seed catalog
- plan/dispatch split
- blocker reporting
- route resolution

### Tool Plane

Implemented:

- manifest-gated execution bridge
- strict command validation

### LLM Lane

Implemented:

- provider config diagnostics
- Open WebUI client
- model catalog normalization
- live model listing
- selection/current/clear
- selection-driven chat apply
- stable response envelope

### AI Alias

Implemented:

```text
/ai currently shares the /llm chat path
```

### Grounding

Partially implemented:

- Wikipedia-first grounded answers
- multi-source fallback with confidence gates
- first deterministic source guard for private contact/location requests and stricter person/workplace claims

Next gap:

```text
correction-aware suppression and a fuller stable grounding result contract
```

## Roadmap By Phase

### Phase 1: Grounding Hardening

Goal:

```text
source-backed factual claims with conservative refusal when evidence is weak
```

### Phase 2: LLM Surface Alignment

Goal:

```text
keep /llm front-door behavior and any legacy config surfaces clearly separated or reconciled
```

### Phase 3: Tool Manifest Hardening

Goal:

```text
tighten manifest validation and tool promotion discipline
```

### Phase 4: Agent Tools Classification And Promotion

Goal:

```text
promote only audited, tested, strict-manifest tools
```

### Phase 5: Session/cache And Memory Features

Goal:

```text
improve temporary context handling without confusing it with memory or grounding
```

## Test Gates

Switch tests:

```bash
python3 -m pytest tests/test_switch_spine.py tests/test_switch_slash_command.py tests/test_switch_matrix_tool.py tests/test_switch_catalog_schema.py tests/test_switch_route_validator_gates.py tests/test_switch_plan_explains_blockers.py
```

LLM tests:

```bash
python3 -m pytest tests/test_llm_front_door.py tests/test_llm_model_selection.py tests/test_llm_config.py tests/test_llm_provider_config.py tests/test_llm_open_webui_client.py tests/test_llm_model_catalog.py tests/test_llm_slash_command.py
```

Core validation rule:

```text
tests should remain offline and mocked unless a branch explicitly scopes live provider behavior
```

## Non-Goals

- do not make `/llm` a second control plane
- do not hardcode provider or backend choices in front doors
- do not bypass `/tool` manifests
- do not invent facts from weak web evidence
- do not add streaming before the envelope is fully stable
- do not add retry/timeout/session memory inside chat execution yet
- do not mix image/audio work into LLM or grounding work

## Success Criteria

The agent succeeds if it can:

- route capability decisions through `/switch`
- execute only through manifest-gated `/tool` paths
- keep `/llm` selection safe and explicit
- apply selected models to chat safely
- return a stable chat envelope
- refuse weak or unsupported factual claims
- preserve offline testability
- keep docs synchronized with behavior

## Final Principle

```text
The runtime decides what is allowed.
The switch spine decides what is routable.
The LLM decides how to phrase it.
The grounding layer decides whether it is true enough to say.
```
