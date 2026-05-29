# Data Agent Retirement Plan

This document records the long-term retirement path for `data_agent/` and the
move toward a slash-command registry as the canonical command surface.

It is a planning document only. It does not move files, delete files, load
registry data, or change runtime behavior.

## Core Architectural Correction

```text
Slash roots are the command system.

The command registry is the canonical slash command catalog.

The old switch-matrix/tool/plugin abstraction is legacy.
```

## Core Runtime Law

```text
Registry describes.
Router selects.
Policy gates.
Runner executes.
Artifacts record.
```

## Permanent Boundaries

```text
Command registration does not authorize execution.

Route decisions do not execute.

Policy decides, but does not answer.

Grounding produces evidence, not guesses.

AgentSpec is not executable.

AgentScript is executable.

Runner executes only explicit approved AgentScript commands.
```

## Current Diagnosis

`data_agent/` currently contains legacy switch-matrix concepts, plugin-style
abstractions, imported tool catalogs, alias systems, generated wrappers, and
mixed runtime assumptions.

The current runtime already behaves more like direct slash-root command
surfaces such as:

```text
/web
/llm
/grep
/ls
/find
/tree
/git
/firefox
/python
/shell
/ground
/patch
```

That means the command system should be modeled as first-class slash roots, not
as a plugin or tool gateway layer.

## Constraints

- Do not delete `data_agent/` yet.
- Do not move files yet.
- Do not add registry loaders yet.
- Do not integrate runtime behavior yet.
- Do not add new plugin, tool, or switch-matrix abstractions.

## Phase 1: Freeze `data_agent`

Goal:

```text
Stop expanding legacy abstractions.
```

Rules:

- no new switch matrix systems
- no new plugin abstractions
- no new tool gateway abstractions
- `data_agent` is legacy and audit-only

Deliverable:

- `docs/data-agent-retirement-plan.md`

## Phase 2: Add Clean Slash Command Data

Goal:

```text
Introduce clean configurable slash command metadata.
```

Future location:

```text
data/commands/
```

Status:

- `data/commands/` fixture schema is started and remains metadata-only.
- this is the future canonical slash-command catalog layer.
- `core/command_registry_loader.py` now reads `data/commands` fixtures as deterministic metadata only.

Initial fixtures should describe slash roots and families only:

```text
/web
/llm
/grep
/ls
/find
/tree
/git
/firefox
/python
/shell
/ground
/patch
```

Rules:

- metadata only
- no execution
- no auto-loading

## Phase 3: Add Registry Loader

Goal:

```text
Load slash command metadata into CommandRegistry.
```

Future API:

```text
load_command_registry(...)
```

Rules:

- deterministic
- metadata only
- no imports
- no execution
- no subprocess

## Phase 4: Add Registry Validation

Goal:

```text
Validate command metadata integrity.
```

Checks:

- duplicate slash roots
- duplicate aliases
- invalid parser families
- invalid policy metadata
- invalid grounding metadata

## Phase 5: Migrate Useful Legacy Data

Goal:

```text
Extract only useful command metadata from data_agent.
```

Possible survivors:

- aliases
- command examples
- route fixtures
- command family descriptions

Likely deletions later, after parity and migration:

- generated wrappers
- plugin assumptions
- imported tool alias clutter
- switch matrix abstractions

Rules:

- migration only
- no execution wiring

## Phase 6: Add NLP Command Resolution

Goal:

```text
Natural language resolves into slash command intent.
```

Flow:

```text
"search the web for cats"
→ /web search cats

"find AgentSpec"
→ /grep AgentSpec

"open firefox"
→ /firefox
```

Critical rule:

```text
NLP selects registered commands only.
NLP does not invent tools.
```

## Phase 7: Add Policy + Grounding Gates

Goal:

```text
Separate:
- routing
- policy
- grounding
- execution
```

Flow:

```text
raw input
→ decode_runtime_input
→ route_runtime_input
→ command registry lookup
→ policy gate
→ grounding gate if needed
→ execution runner
```

## Phase 8: Replace Batch Runner If/Elif Routing

Goal:

```text
Replace scattered raw dispatch.
```

Replace:

```python
if command == ...
elif command == ...
```

With:

```python
registry-driven dispatch
```

Rules:

- behavior-preserving first
- execution migration later

## Phase 9: Retire Legacy Compatibility Surfaces

Potential retirements:

```text
/switch
/tool
plugin gateway abstractions
switch matrix terminology
```

Only after:

```text
tests prove nothing depends on them
```

## Phase 10: Remove or Archive `data_agent`

Goal:

```text
Remove legacy architecture safely.
```

Rules:

- only after migration complete
- only after parity tests pass
- only after runtime no longer depends on it

Possible outcome:

```text
archive/data_agent_legacy/
```

or:

```text
full removal
```

## Non-Negotiable Safety Rules

```text
No execution from config.

No auto-import execution.

No runtime authority from metadata.

No plugin auto-loading.

No dynamic execution from registry entries.

All execution remains explicit and policy-gated.
```

## Current Status

- `data_agent/` is legacy and remains in place for now.
- `data/commands/` fixture schema is started as the future canonical slash-command catalog layer.
- the command registry is the canonical slash-command catalog direction.
- no loader, migration, or runtime integration has been implemented yet.
- the retirement plan is intentionally staged so behavior stays stable while parity tests and registry metadata harden.
