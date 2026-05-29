# Roadmap

This is the cleaned active roadmap for `agent`.

## Current thesis

Build a minimal Linux CLI agent core where slash roots are the command system and the command registry is the canonical slash-command catalog.

Short Codex prompts are the default. Use giant prompts only for dangerous architecture changes.

## Packaging Hardening

- staged patch ZIPs are the canonical patch workflow package format
- patch ZIPs include `change.patch`, metadata, tests, and one-command stage scripts
- one command equals one stage and then stop: inspect, preflight, apply, test, report, commit, push
- Codex is a stage runner only unless explicitly scoped otherwise
- patch packaging validates staged/untracked completeness before ZIP build
- patch packaging emits deterministic metadata and blocks false-success partial commits
- new source/test/docs files must be explicitly staged before packaging
- patch runner validates reconstructed git state after apply and before commit
- staged additions, modifications, and deletions must survive the apply-to-commit lifecycle
- the patch runner remains the final policy gate, but the builder now proves package completeness earlier

## Deterministic Response Policy Gate

- started as a deterministic runtime guard layer before answer generation
- detects music/reference prompts, lyrics requests, ambiguous music entities, reversed phrasing, and source-confirmation-needed cases
- returns decisions only; it does not answer, fetch, search, or execute
- full copyrighted lyrics requests are refused
- unresolved music entities clarify instead of hallucinating
- runtime integration is the next milestone

## Runtime Prompt Pipeline Audit

- `docs/runtime-pipeline.md` records the current live prompt flow and fallback risks
- `docs/runtime-router-redesign.md` records the planned typed runtime input pipeline
- `docs/runtime-router-audit-roadmap.md` records the phased router migration roadmap
- Frontend interacts.
- Spec describes.
- Policy gates.
- Grounding proves.
- Compiler emits.
- Runtime executes.
- Artifacts record.
- AgentSpec is not executable.
- AgentScript is executable.
- agentspec never executes.
- core/compiler never executes.
- response_policy decides, but does not answer.
- grounding produces evidence, not guesses.
- runner executes only explicit approved AgentScript commands.
- no hidden autonomy rule: inspect, plan, dry-run, approve, apply, and report remain distinct
- OS integration is later Phase 8.
- Application integration is later Phase 9.
- Cross-platform runtime is later Phase 10.

## Runtime Router Redesign

- replace raw `if`/`elif` prompt routing with typed input specs before changing runtime behavior
- keep slash commands and natural language on the same typed decode path
- preserve policy gating before routing and handling
- preserve structured results and artifacts from handlers

## Command Registry Audit

- document the current command, plugin, and tool surfaces before any execution migration
- keep the registry dependency-free, table-driven, inspectable, and non-executing
- `core/command_registry.py` now exists as the dependency-free command registry schema and default fixture layer
- `core/execution_dispatch.py` now exists as inspect-only registry-backed execution dispatch scaffolding
- `core/execution_dispatch_render.py` now exists as inspect-only dispatch-plan render helpers
- `docs/render` is the inspect-only registry docs rendering surface in the schema layer
- `core/command_registry_render.py` renders registry metadata deterministically as inspect-only JSON and markdown
- command registry route parity tests now compare typed preview modes against registry metadata before execution integration
- dispatch-plan parity coverage now compares registry-backed plans against command registry metadata before execution integration
- the first behavior-identical execution migration now starts with the read-only repo surfaces `/read`, `/ls`, `/tree`, and `/find`
- `core.batch_runner` uses registry-backed dispatch planning for those repo-local surfaces while preserving behavior
- `/commands` now previews as the help route in `route_runtime_input()`, closing the preview gap with command registry metadata
- slash roots are the canonical command surfaces; `/web`, `/search`, `/llm`, `/vision`, `/image`, `/git`, `/grep`, `/ls`, `/tree`, `/find`, `/python`, `/shell`, `/firefox`, `/ground`, and `/patch` remain first-class in dispatch metadata
- treat `core.batch_runner.run_command()` dispatch as the execution surface to be replaced later
- treat `core/runtime_decoder/router.py` as the inspect-only preview surface
- treat `data_agent/` as legacy until the retirement plan says to freeze, migrate, and eventually archive it
- `/switch`, `/tool`, plugin language, tool gateway language, and switch matrix language are legacy compatibility only
- keep parser-family boundaries explicit between typed runtime whitespace semantics and batch `shlex.split()` compatibility

## Data Agent Retirement

- `docs/data-agent-retirement-plan.md` records the staged path from legacy `data_agent/` catalogs to command-registry-backed slash metadata
- `data/commands/` is the future canonical slash-command catalog fixture layer
- do not delete or move `data_agent/` yet
- do not integrate runtime behavior yet
- the command registry is the canonical slash-command catalog direction
- the `data/commands` fixture schema is started and remains metadata-only
- slash roots are first-class command surfaces and the `data/commands` fixtures are the future canonical catalog layer
- `core/command_registry_loader.py` loads `data/commands` fixtures as deterministic metadata only

## Immediate Next Milestone

Agent CLI backend / encoder frontend pivot:

- pause live semantic route execution work
- keep semantic routing and encoder layers frontend-only
- keep `agent-cli.py` as the backend execution boundary
- plain text fallback must not route into semantic route execution
- semantic router proposes and diagnoses only; it does not execute
- `RouteDecision` is inspect-only and does not authorize answering, fetching, searching, mutation, tool use, or execution
- backend execution must enter through explicit `agent-cli.py` commands or approved AgentScript runner paths
- decoder/final response must summarize validated backend packets and must not invent missing tool results
- no live terminal wiring until AgentSpec, AgentScript, validation, capability checks, and evidence packet boundaries are complete
- next implementation target is an `agent-cli.py` structured backend packet MVP, not live route execution

Next implementation candidates:

- `agent-cli.py` structured backend packet output
- encoder-to-agent-cli request schema
- AgentScript validation gap
- LaneInvocation compiler test
- route diagnostics cleanup
- patch runner verification

Preserve from the AgentSpec MVP foundation:

- keep deterministic schema/rendering/decoding/routing helpers
- keep dispatch preview deterministic and non-executing
- keep JSON Schema export and policy validation deterministic
- keep example specs and golden outputs deterministic
- keep route and dispatch decisions exact across helpers and CLI
- no execution, mutation, tools, agents, or orchestration inside `agentspec`

## Phase 1 — Hygiene

- restore clear README and active docs
- remove generated caches from git
- add `.gitignore` for Python caches and local data
- keep historical docs out of the active path unless clearly archived

## Phase 2 — Switch clarity

- document switch state schema
- verify `/switch` never executes tools
- verify family preference is only a ranking hint
- add route validator tests for blocked, read-only, plan-only, and dispatchable states

## Phase 3 — Tool bridge hardening

- lint every manifest
- reject unknown flags consistently
- verify command path allowlist behavior
- test timeout and stdout/stderr bounds
- capture last tool output predictably

## Phase 4 — Router cleanup

- keep exact slash commands first
- keep deterministic aliases before semantic routing
- keep natural-language routing narrow and auditable
- ensure `/paste` uses normal routing after collection

## Phase 5 — LLM front door

- keep `/llm` and `/ai` behind switch policy
- centralize provider config
- normalize chat response envelopes
- keep model listing and model selection inspectable
- keep any future AgentSpec LLM decoder optional and future-only

## Phase 6 — Retrieval and grounding

- keep session cache temporary
- keep knowledge index persistent and explicit
- add source-backed response discipline for factual claims
- separate grounding from tool execution

## Phase 7 — Tool ecosystem

- move large external tool suites outside the core repo
- keep connector manifests and legacy audits out of runtime behavior until the retirement plan says otherwise
- add manifest schema docs and tests

## Phase 8 — OS integration

- add explicit operating-system integration points only after the contract foundation is stable
- keep system-level actions policy-gated and reviewable
- avoid implicit background automation

## Phase 9 — Application integration

- add application-specific integration surfaces after OS boundaries are explicit
- keep app-level connectors deterministic and observable
- keep execution paths manifest- or policy-gated

## Phase 10 — Cross-platform runtime

- generalize the runtime carefully after contract, OS, and application boundaries are stable
- avoid hidden platform behavior
- preserve the same inspect/plan/dry-run/approve/apply/report discipline across platforms

## Runtime Input Models

- `core/runtime_decoder/models.py` starts the typed input spec layer
- `core/runtime_decoder/slash.py` starts deterministic slash command decoding
- slash root matching is case-insensitive and preserves user-visible casing
- slash decoder covers live command families like `/help`, `/commands`, `/state`, `/config`, `/fs`, `/python`, `/shell`, `/remember`, `/memory`, and `/plugin*`
- `core/runtime_decoder/decoder.py` starts the unified deterministic runtime input decoder
- `decode_runtime_input(text)` is the unified runtime input decoder entrypoint
- `classify_natural_input(text)` remains decode-only and non-executing
- decoder trace metadata is deterministic and inspect-only
- `core/runtime_decoder/router.py` starts inspect-only route decisions over typed `InputSpec` values
- `agent-cli.py` debug route metadata now comes from typed decode plus typed preview route decisions
- execution parity tests now compare typed route preview against current `core.batch_runner.run_command()` behavior and record known gaps
- `core.batch_runner` now has an internal handler registry for behavior-identical execution dispatch
- parser boundary is explicit: `runtime_decoder` uses whitespace tokenization while `core.batch_runner` keeps `shlex.split()` compatibility
- active execution still lives in `core.batch_runner.run_command()`
- replacing `agent-cli.py` debug route duplication is a future milestone
- future router phases should add parity tests, a batch handler registry, a documented `shlex.split()` parser boundary, policy preview, and visible `chat_fallback_unprotected` mode before execution integration
- add slash and natural-language decoders later
- keep the model layer non-executing and routing-free

<!-- agent-three-llm-lanes:start -->
## Three LLM lanes

Current target model:

```text
/prompt  direct base LLM lane
/ground  grounded/RAG evidence lane with final LLM synthesis
/summon  persona/session control; explicit persona-routed prompt via /summon prompt
```

Legacy answer-like prompt-template command names are unwired and should not receive new architecture work. The next grounding milestone is a provider adapter layer and a stable EvidencePacket schema behind `/ground`.
<!-- agent-three-llm-lanes:end -->

<!-- agent-grounded-resolver-memory:start -->
## Grounded resolver roadmap memory

Current lane state:

```text
/prompt        direct LLM lane
/ground        primary grounded/RAG lane and evidence builder
/summon        persona/session control
/summon prompt explicit prompt to summoned persona state
```

Checked:

- [x] document `/ground` as the primary grounded/RAG path
- [x] unwire old answer-like command names instead of aliasing them
- [x] keep `/prompt` direct and separate from summon/persona routing
- [x] add `/summon prompt` as the explicit persona prompt path
- [x] repair the first deterministic resolver layer: boilerplate normalization, song lookup normalization, entity-title gate, and short ambiguous-location guard

Unchecked:

- [ ] define `GroundingQuery -> EvidencePacket -> render/synthesize` as the stable pipeline
- [ ] make `/ground` diagnostics and answer synthesis read from the same packet
- [ ] replace hand-rolled fetch/extraction pieces only through provider adapters
- [ ] add optional provider packages in phases, starting small and local before API-backed services
- [ ] add groundedness evals after EvidencePacket output is stable
<!-- agent-grounded-resolver-memory:end -->

<!-- agent-legacy-semantic-stack:start -->
## Legacy semantic stack

The semantic router, AgentSpec, AgentScript, and encoder layers are no longer implementation targets. They are archive/reference material only and should not drive routing, authorization, or runtime execution.

Roadmap work should move to `/ground` EvidencePacket/provider adapters and keep `/prompt` and `/summon` separate.
<!-- agent-legacy-semantic-stack:end -->
