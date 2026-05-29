# Command Registry Audit

This document audits the current command, plugin, and tool surfaces and lays out the design for a future dependency-free command registry.

It is documentation only. It does not change runtime behavior.

## Current Picture

- `core.batch_runner.run_command()` is the live execution router.
- `agent-cli.py` emits diagnostic route metadata only.
- `core/runtime_decoder/router.py` produces inspect-only `RouteDecision` values.
- `core/command_registry.py` now provides the dependency-free command registry schema and default fixtures only.
- `core/command_registry_render.py` renders registry metadata deterministically as inspect-only JSON and markdown.
- `core/command_registry_loader.py` reads `data/commands` fixtures as deterministic metadata only.
- `core/execution_dispatch.py` provides inspect-only registry-backed execution dispatch scaffolding and dispatch plans.
- `core/execution_dispatch_render.py` renders dispatch plans deterministically as inspect-only JSON and markdown.
- command registry route parity tests compare typed preview modes against registry metadata before execution integration.
- dispatch-plan parity coverage compares registry-backed plans against registry metadata before execution integration.
- `core.batch_runner` now begins a behavior-identical execution migration for the read-only repo surfaces `/read`, `/ls`, `/tree`, and `/find`.
- `/commands` now previews as the help route in `route_runtime_input()`, closing the preview gap with command registry metadata.
- `agentspec/` is a separate contract layer and does not execute runtime commands.
- `data_agent/` holds catalog and metadata surfaces for switches, tools, aliases, and TUI contracts.
- There is no top-level `plugins/` directory in this repo state.
- There is no top-level `tools/` directory in this repo state.

## Surface Audit

| Surface | Current Role | Parser Family | Current Status | Registry Disposition |
| --- | --- | --- | --- | --- |
| `agent-cli.py` debug route payload | Diagnostic preview only | internal_only | keep | keep; source typed preview from `decode_runtime_input()` + `route_runtime_input()` |
| `docs/render` | inspect-only registry docs rendering front door | internal_only | keep | keep as a registry metadata surface; rendering helpers live in `core/command_registry_render.py` |
| `/switch` | control-plane front door for switch helpers | batch_runner_shlex | keep | replace scattered dispatch with a command registry |
| `/tool` | tool invocation gateway into imported tool payloads | batch_runner_shlex | replace with command registry | requires policy and approval gates |
| `/llm` | LLM config/status/preset front door | batch_runner_shlex | keep | replace scattered dispatch with a command registry |
| `/codex` | inspect-only Codex prompt/package front door | batch_runner_shlex | keep | replace scattered dispatch with a command registry |
| `/patch` | patch front door | batch_runner_shlex | keep | replace scattered dispatch with a command registry |
| `/search` | repo/web search front door | batch_runner_shlex | keep | replace scattered dispatch with a command registry |
| `/web` | fetch/extract/search front door | batch_runner_shlex | keep | replace scattered dispatch with a command registry |
| `/ground` | grounded evidence/report front door | batch_runner_shlex | keep | replace scattered dispatch with a command registry |
| `/vision` | reserved first-class multimodal dispatch family placeholder | internal_only | unknown until parity tests | metadata-only dispatch scaffolding only |
| `/image` | reserved first-class multimodal dispatch family placeholder | internal_only | unknown until parity tests | metadata-only dispatch scaffolding only |
| `/read`, `/ls`, `/tree`, `/find` | repo-local inspection front doors | batch_runner_shlex | keep | replace with a repo command-registry surface |
| unsupported slash handling | explicit rejection path | batch_runner_shlex | keep | registry should preserve the unsupported surface as an inspectable terminal state |
| natural-language fallback | direct chat fallback | internal_only | unknown until parity tests | later policy/guard work should make direct fallback visible and inspectable |
| `data_agent/switches/capabilities.seed.json` | switch capability catalog | internal_only | keep | registry-adjacent data surface |
| `data_agent/switches/linux_cli_switches.json` | switch validator catalog with mutable command examples | internal_only | unknown until parity tests | likely registry-adjacent, but it contains operational commands that need audit before reuse |
| `data_agent/switches/switch_profiles.json` | switch profile catalog | internal_only | keep | registry-adjacent data surface |
| `data_agent/nlp/tool_families.json` | tool family catalog for `/switch` | internal_only | keep | registry-adjacent data surface |
| `data_agent/nlp/route_examples.json` | route examples and future validator fixtures | internal_only | keep | audit fixture, not runtime dispatch |
| `data_agent/nlp/route_test_matrix.json` | route regression matrix | internal_only | keep | audit fixture, not runtime dispatch |
| `data_agent/nlp/imported_tool_aliases.json` | legacy imported tool alias catalog | internal_only | legacy/archive candidate | keep out of the live registry until parity tests prove it is needed |
| `data_agent/nlp/imported_tool_exact_aliases_01.json` | legacy exact alias catalog | internal_only | legacy/archive candidate | same as above |
| `data_agent/reports/imported_tools_report.json` | imported tool audit report | internal_only | keep | report artifact, not runtime dispatch |
| `data_agent/plugins/cli/*.json` | active CLI manifest catalog | internal_only | keep | registry-adjacent manifest data |
| `data_agent/plugins/cli_disabled/*` | disabled legacy manifest/tool data | internal_only | legacy/archive candidate | do not route from here without parity tests and explicit audit |
| `data_agent/tui/agent-tool-runner.tui.json` | TUI workflow contract | internal_only | legacy/archive candidate | external UI workflow, not live runtime routing |
| `data_agent/tui/generated_agent_tool_runner.py` | generated TUI launcher | internal_only | legacy/archive candidate | generated UI wrapper, not registry source of truth |

## Duplicated Or Ambiguous Boundaries

- `/switch` currently spans control-plane intent, family preferences, and tool-selection metadata.
- `/tool` currently spans manifest-gated tool invocation and imported tool aliases.
- `/search` currently spans repo search and web search on one surface.
- `/web` currently spans fetch, extract, and web search on one surface.
- `/ground` currently spans repo grounding, collections, search, saved reports, and report inspection on one surface.
- `/read`, `/ls`, `/tree`, and `/find` are repo-local inspection surfaces that should remain simple-token only.
- `agent-cli.py` debug route metadata and `core.batch_runner.run_command()` execution routing are now closer than before, but execution still lives in `run_command()`.
- runtime decoder preview modes are typed and inspect-only; they are not execution handlers.
- parser semantics differ between typed runtime decoding and batch execution.

## Parser Boundary

- `runtime_decoder` uses deterministic whitespace tokenization.
- `runtime_decoder` does not use `shlex`.
- `runtime_decoder` preserves `raw_text` exactly.
- `runtime_decoder` preserves user-visible token casing.
- `core.batch_runner` may keep `shlex.split()` for current CLI and batch compatibility.
- `core.batch_runner` tokenization is execution compatibility, not typed runtime semantics.
- typed args are diagnostic-only and must not be treated as execution args yet.
- future execution integration must decide whether a command belongs to typed runtime whitespace semantics, legacy batch `shlex` semantics, or a command-specific parser.

## Proposed Future Registry Shape

The future command registry should be dependency-free, inspectable, and table-driven.

Possible module names:

- `core/command_registry.py`
- `core/runtime_registry.py`

Possible public API:

- `CommandRegistration`
- `CommandRegistry`
- `register_command(...)`
- `get_command(...)`
- `list_commands()`
- `validate_registry()`

Required registration fields:

- `name`
- `surface`
- `mode`
- `handler_name`
- `description`
- `input_kind`
- `allowed_in_batch`
- `requires_policy`
- `requires_grounding`
- `requires_approval`
- `mutates_state`
- `inspect_only`
- `parser_family`
- `aliases`
- `metadata`

Parser family values should stay explicit:

- `runtime_decoder_simple`
- `batch_runner_shlex`
- `internal_only`

## Registry Invariants

- registry lookup does not execute.
- route decisions do not execute.
- registry metadata does not authorize answering.
- response_policy decides, but does not answer.
- grounding produces evidence, not guesses.
- AgentSpec is not executable.
- AgentScript is executable.
- runner executes only explicit approved AgentScript commands.
- the registry must distinguish preview route modes from execution handlers.
- the registry must be inspectable before it is executable.
- the registry should support docs and tests without requiring runtime side effects.
- no PyPI router package is used.

## Suggested Surface Classification For Future Registry Work

- Keep: `agent-cli.py` debug route metadata, switch catalogs, route fixtures, and repository inspection front doors.
- Keep: `docs/render` as an inspect-only registry docs rendering surface.
- Keep: route parity tests as the guardrail for preview-mode and registry metadata alignment.
- Replace with command registry: the scattered raw execution dispatch in `core.batch_runner.run_command()`.
- Legacy/archive candidate: imported tool alias catalogs, disabled legacy manifests, and generated TUI wrappers.
- Unknown until parity tests: any surface where parser semantics or approval semantics are not fully settled.

## Registry And Route Preview Relationship

- `RouteDecision` remains the typed preview model.
- `CommandRegistration` would be the execution metadata model.
- preview modes are not execution handlers.
- route preview should inform registry design, but not execute anything.
- switch matrix should become a `/commands` registry surface, not a plugin/tool subsystem.
- `/commands` already previews as the help route in `route_runtime_input()`, so typed preview and registry metadata now align on the preview surface.
- the current code now has the schema/fixture layer only; execution integration remains future work.
