# Runtime Router Redesign

This document proposes the next runtime input pipeline while keeping current
runtime behavior unchanged.

## Current Pivot

Runtime router redesign is frontend/encoder work until explicitly promoted. `agent-cli.py` is the backend execution boundary. Typed input specs and route decisions may propose or preview explicit backend requests, but they must not execute or authorize final answers.

## Goal

Replace raw `if`/`elif` prompt routing with typed input specs before any runtime
behavior changes.

The target flow is:

`raw user input` -> `decode` -> `typed InputSpec` -> `policy gate` ->
`deterministic router / encoder preview` -> `explicit agent-cli.py backend request` ->
`structured backend result packet`

## Principle

Slash commands and natural language both decode into typed specs.

That means the runtime should stop treating raw text as the primary routing
primitive. The decoder should produce an explicit `InputSpec` subtype first,
then the router should make a deterministic decision from that typed object.

## Current Input Families

The unified runtime input pipeline should account for:

- `/switch`
- `/tool`
- `/ground`
- `/web`
- `/search`
- `/patch`
- natural language prompts
- AgentSpec JSON/Markdown prompts
- future AgentScript input

## Target Spec Types

The decoder should eventually normalize input into one of these deterministic
specs:

- `InputSpec`
- `SlashCommandSpec`
- `SwitchCommandSpec`
- `GroundCommandSpec`
- `WebCommandSpec`
- `SearchCommandSpec`
- `PatchCommandSpec`
- `ToolCommandSpec`
- `AgentTaskInputSpec`
- `FactualAnswerSpec`
- `UnknownInputSpec`

## Future Packages

The next runtime-router layer should live in small deterministic modules:

- `core/runtime_decoder/models.py`
- `core/runtime_decoder/slash.py`
- `core/runtime_decoder/natural.py`
- `core/runtime_decoder/policy.py`
- `core/runtime_decoder/router.py`

## Current Progress

`core/runtime_decoder/models.py` now exists and contains the initial typed
runtime `InputSpec` models only. No parser, router, or runtime integration is
added yet.

`core/runtime_decoder/slash.py` now exists and decodes slash commands into
typed `InputSpec` models only. It does not route, execute, or integrate with
runtime behavior.

Root matching is case-insensitive, but decoded command and argument casing are
preserved for user-visible output.

Current slash coverage includes `/help`, `/commands`, `/state`, `/config`,
`/fs`, `/python`, `/shell`, `/remember`, `/memory`, and `/plugin*` families.

`core/runtime_decoder/decoder.py` now exists as the unified deterministic
runtime input decoder entrypoint. It delegates slash input to the slash
decoder and non-slash input to the natural classifier.

`core/runtime_decoder/natural.py` now exists and classifies natural input into
typed `InputSpec` models only. It does not route, answer, ground, resolve
entities, decide policy, execute, or call models.

`core/runtime_decoder/decoder.py` also adds deterministic trace metadata to
every emitted spec. The metadata is diagnostic only and does not imply answer
permission or execution permission.

`core/runtime_decoder/router.py` now exists and turns typed `InputSpec` values
into inspect-only route decisions. It does not execute, call handlers, ground,
fetch, search, or decide response policy.

`agent-cli.py` debug route metadata now comes from `decode_runtime_input(text)`
plus `route_runtime_input(spec)`, so the diagnostic preview is typed and
inspect-only even though `core.batch_runner.run_command()` still owns the live
execution path.

Execution parity tests now compare typed route preview against current
`core.batch_runner.run_command()` behavior and record known gaps before any
execution migration begins.

`core.batch_runner` now has an internal handler registry, but it remains a
behavior-identical execution layer and is not yet driven by `RouteDecision`.

Active execution still lives in `core.batch_runner.run_command()`.

Replacing `agent-cli.py` debug route duplication with typed route decisions is
a future milestone.

The detailed audit and migration plan lives in
`docs/runtime-router-audit-roadmap.md`. That roadmap keeps `RouteDecision`
values as preview modes until parity tests, handler registry work, parser
boundary documentation for `shlex.split()`, policy preview, and explicit
`chat_fallback_unprotected` diagnostics are in place.

## Required Guarantees

The redesigned pipeline must preserve these guarantees:

- no raw prompt directly triggers tools
- no factual prompt bypasses policy
- no factual prompt bypasses grounding when grounding is required
- no private-person lookup leaks PII
- no full copyrighted lyrics output
- no unsafe cyber exploit generation
- unknown input clarifies instead of hallucinating
- handlers return structured results/artifacts

## Architecture Boundary

This is a planning document only.

It does not change runtime behavior yet.
It does not add AgentSpec execution.
It does not wire `core.response_policy` into the live path yet.
It does not replace current routing code yet.

The point is to make the future runtime router contract explicit before any
implementation work begins.

## Command Registry Boundary

The next execution-facing layer after typed route decisions should be a dependency-free command registry.

- `core/command_registry.py` now exists as the schema and fixture layer only.
- `docs/render` is the inspect-only registry docs rendering surface in the schema layer.
- `core/command_registry_render.py` renders registry metadata deterministically as inspect-only JSON and markdown.
- `core.batch_runner` has begun a behavior-identical execution migration for the read-only repo surfaces `/read`, `/ls`, `/tree`, and `/find` by consulting registry-backed execution dispatch planning while preserving behavior.
- `RouteDecision` is preview-only and does not execute.
- `CommandRegistration` should be the execution metadata model, not a policy engine.
- registry lookup must not execute.
- registry metadata must distinguish preview route modes from execution handlers.
- command registry route parity tests compare typed preview modes against registry metadata before execution integration.
- `/commands` now previews as the help route in `route_runtime_input()`, closing the preview gap with command registry metadata.
- registry fields should include surface, mode, handler name, parser family, approval requirements, grounding requirements, and mutability.
- switch matrix should become a `/commands` registry surface, not a plugin/tool subsystem.
- plugins/tools are legacy until audited.
- no PyPI router package is used.

## Parser Boundary

The typed runtime decoder and the batch runner do not share the same parser.
That boundary must remain explicit.

- `runtime_decoder` uses deterministic whitespace tokenization.
- `runtime_decoder` preserves `raw_text` exactly.
- `runtime_decoder` normalizes `normalized_text` with trimming and collapsed
  whitespace.
- `runtime_decoder` does not use `shlex`.
- `runtime_decoder` does not preserve shell quoting semantics.
- `core.batch_runner.run_command()` may keep `shlex.split()` for current CLI
  and batch compatibility.
- `core.batch_runner` tokenization is execution compatibility, not typed
  runtime semantics.
- typed `argv` and debug `argv` must not be treated as execution `argv`.
- typed route preview is diagnostic only.
- do not use typed args as execution args until a future milestone explicitly
  migrates that command family.
- future execution integration must explicitly decide whether a command belongs
  to typed runtime whitespace semantics, legacy batch `shlex` semantics, or a
  command-specific parser.

Examples:

- `/tool switch.matrix "quoted value"` may tokenize differently in
  `runtime_decoder` vs `batch_runner`.
- typed decoder output is safe for classification and diagnostics.
- batch runner token output remains the source for current execution.
