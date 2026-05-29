# Codex Handoff

This is the handoff for continuing the agent project with Codex CLI or another coding agent.


## Current Pivot

Agent is now being recovered around this split:

```text
encoder / semantic-router frontend
-> explicit agent-cli.py backend command or packet request
-> structured backend result packet
-> decoder/final response over validated packet evidence
```

`agent-cli.py` is the backend execution boundary. Semantic routing and encoder
layers remain frontend-only and must not execute, fetch, search, mutate, call
tools, call the LLM, or bypass validation. Live semantic route execution remains
paused.

Codex should act as a repo eyes/hands and patch-stage runner only. It should run
one requested staged patch script at a time, paste exact output, and stop. It
should not manually edit files, invent code changes, create patches, commit, or
push unless the requested stage explicitly does that.

## Repository State

Primary repo path used during development:

```text
~/Downloads/agent
```

Current intended front door:

```text
agent-cli.py
```

`agent.py` is legacy/deprecated for now. It may be renamed/replaced later after the CLI path is solid.

Short Codex prompts are the default. Use giant prompts only for dangerous architecture changes.

## Current Architecture

- `core/` contains reusable agent kernel pieces.
- `agent-cli.py` is the non-interactive terminal/batch entrypoint.
- `core/batch_runner.py` routes supported non-interactive slash surfaces.
- `core/patch_frontdoor.py` parses/builds `/patch` commands.
- staged patch ZIPs are the canonical patch workflow packages.
- staged patch ZIPs contain `change.patch`, metadata, `tests/`, and `stages/00_inspect.sh` through `stages/06_push.sh`.
- `scripts/agent_patch_runner.py` applies legacy patch ZIPs with validation, reports, rollback, and optional commit/push.
- `scripts/make_patch_package.py` builds legacy patch ZIPs from real `git diff` output.
- current front doors in `core.batch_runner` cover `/read`, `/ls`, `/tree`, `/find`, `/search repo`, `/search web`, `/web fetch`, `/web extract`, `/web search`, `/ground repo`, `/ground collect`, `/ground search`, `/ground reports`, `/ground show`, `/codex`, `/llm`, and `/patch`
- `/switch`, `/tool`, plugin language, tool gateway language, and switch matrix language are legacy compatibility only
- `core/scrape`, `core/search`, and `core/ground` are the reusable deterministic layers currently in play
- `core/web` is the fetch/search/extract web engine layer built on top of `core/scrape`
- there are no `core/llm/` or `core/codex/` package directories yet; those front doors live as `core.llm_frontdoor` and `core.codex_frontdoor`
- artifact lanes are local filesystem only:
  - `reports/web-cache/`
  - `reports/ground/`
  - `reports/patch-runs/`
- no hidden autonomy: inspect, plan, dry-run, approve, apply, and report are distinct stages
- `docs/runtime-pipeline.md` records the current live prompt pipeline, direct fallback points, and the Typed Agent OS boundary
- `docs/runtime-router-redesign.md` records the planned typed runtime input pipeline and spec boundary
- `docs/runtime-router-audit-roadmap.md` records the phased router migration roadmap
- `docs/data-agent-retirement-plan.md` records the staged retirement path for legacy `data_agent/` abstractions
- patch packaging now validates staged/untracked completeness before building ZIPs
- patch packaging now emits deterministic metadata and blocks false-success partial commits
- new source/test/docs files must be explicitly staged before packaging
- patch runner now validates reconstructed git state before commit
- staged additions, modifications, and deletions must survive the apply-to-commit lifecycle
- package manifest enforcement happens after apply and before commit
- `core/response_policy` is a deterministic runtime guard layer for factual/reference prompts
- `core/response_policy` currently returns decisions only and is not yet wired into `agent.py` or `agent-cli.py`
- full copyrighted lyrics requests are refused by `core/response_policy`
- unresolved music entities clarify instead of hallucinating a factual answer
- AgentSpec MVP contract foundation is started
- AgentSpec deterministic decode/router MVP is started
- AgentSpec dispatch dry-run/render MVP is started
- AgentSpec examples and contract docs hardening is started
- AgentSpec route consistency hardening is started
- `python -m agentspec validate examples/agentspec/task.json` works
- `python -m agentspec decode examples/agentspec/task.json` works
- `python -m agentspec route examples/agentspec/task.json` works
- `python -m agentspec dispatch examples/agentspec/task.json --dry-run` works
- `python -m agentspec dispatch examples/agentspec/task.json --render` works
- `python -m agentspec validate examples/agentspec/repo_patch.json` works
- `python -m agentspec validate examples/agentspec/docs_only.json` works
- `python -m agentspec validate examples/agentspec/inspect.json` works
- `python -m agentspec validate examples/agentspec/validation.json` works
- `python -m agentspec route examples/agentspec/repo_patch.json` works
- `python -m agentspec route examples/agentspec/docs_only.json` works
- `python -m agentspec route examples/agentspec/inspect.json` works
- `python -m agentspec route examples/agentspec/validation.json` works
- `python -m agentspec dispatch examples/agentspec/repo_patch.json --dry-run` works
- `python -m agentspec dispatch examples/agentspec/docs_only.json --dry-run` works
- `python -m agentspec dispatch examples/agentspec/inspect.json --dry-run` works
- `python -m agentspec dispatch examples/agentspec/validation.json --dry-run` works
- `docs/agentspec-roadmap.md` explains the AgentSpec contract boundary
- route and dispatch decisions are consistent across CLI and helper paths
- `python -m agentspec render examples/agentspec/task.json --target codex` works
- `python -m agentspec render examples/agentspec/task.json --target verify-sh` works
- `python -m agentspec render examples/agentspec/task.json --target checklist` works
- `python -m agentspec export-schema` works
- AgentSpec validation rejects malformed JSON and simple policy conflicts
- `agentspec` is schema/rendering/decoding/routing/dispatch-preview only; it does not execute tasks, mutate files, call tools, or orchestrate agents
- dispatch is dry-run/render-only; executor stays outside `agentspec`
- example specs validate, route, and dispatch deterministically
- route JSON and dispatch JSON are exact, deterministic, and consistent across helpers and CLI
- future AgentSpec phases may add `ExecutionSpec`, `ReviewSpec`, `PlanSpec`, `MemorySpec`, or an optional LLM decoder later
- AgentSpec is not executable; AgentScript is the future executable artifact
- response_policy decides, but does not answer
- grounding produces evidence, not guesses
- runner executes only explicit approved AgentScript commands
- no hidden autonomy rule: inspect, plan, dry-run, approve, apply, and report remain distinct
- raw prompt routing is being redesigned toward typed input specs before runtime behavior changes
- runtime_decoder InputSpec models are started in `core/runtime_decoder/models.py`
- deterministic slash command decoding is started in `core/runtime_decoder/slash.py`
- slash decoder root matching is case-insensitive while preserving user-visible command and argument casing
- slash decoder now covers more live command families like `/help`, `/commands`, `/state`, `/config`, `/fs`, `/python`, `/shell`, `/remember`, `/memory`, and `/plugin*`
- deterministic runtime input decoder is started in `core/runtime_decoder/decoder.py`
- `decode_runtime_input(text)` is the unified runtime input decoder entrypoint
- `classify_natural_input(text)` is deterministic and emits typed `InputSpec` models only
- runtime decoder trace metadata is deterministic and inspect-only
- decode results carry `decoder`, `decoder_version`, `input_family`, and `classification_reason`
- runtime route decisions are started in `core/runtime_decoder/router.py`
- `route_runtime_input(spec)` consumes typed `InputSpec` values and returns inspect-only route decisions
- `agent-cli.py` debug route metadata now uses `decode_runtime_input(text)` plus `route_runtime_input(spec)`
- execution parity tests now compare typed route preview against current `core.batch_runner.run_command()` behavior and record known gaps
- `core.batch_runner` now has an internal handler registry for behavior-identical execution dispatch
- parser boundary is explicit: `runtime_decoder` uses whitespace tokenization while `core.batch_runner` keeps `shlex.split()` compatibility
- active execution still lives in `core.batch_runner.run_command()`
- replacing `agent-cli.py` debug route duplication is a future milestone
- `docs/command-registry-audit.md` records the current command, plugin, and tool surface audit
- `core/command_registry.py` now provides the dependency-free command registry schema and default fixtures only
- slash roots are the command system; the command registry is the canonical slash-command catalog direction
- `data/commands/` is the future canonical slash-command catalog fixture layer
- command registry lookup and construction are inspect-only metadata helpers; no execution or handler calls were added
- handler registry/execution integration remains future work
- `data_agent/` remains in place for now as legacy compatibility; do not move or delete it until the retirement plan says to do so
- `data/commands/` fixture schema has started; loader exists as metadata-only and no runtime integration exists yet
- `core/command_registry_loader.py` now reads `data/commands` fixtures as deterministic metadata only
- `docs/render` is an inspect-only registry docs rendering surface in the command registry schema
- `core/command_registry_render.py` renders registry metadata deterministically as inspect-only JSON and markdown
- `core/execution_dispatch.py` provides inspect-only registry-backed execution dispatch scaffolding and plans
- `core/execution_dispatch_render.py` renders dispatch plans deterministically as inspect-only JSON and markdown
- dispatch-plan parity coverage now compares registry-backed plans against command registry metadata before execution integration
- `core.batch_runner` now uses registry-backed dispatch planning for the read-only repo surfaces `/read`, `/ls`, `/tree`, and `/find` while preserving behavior
- slash roots are the canonical command surfaces, with `/web`, `/llm`, `/vision`, and `/image` treated as first-class families in dispatch metadata
- command registry route parity tests now compare typed `RouteDecision` preview modes against registry metadata before execution integration
- `/commands` now previews as the help route in `route_runtime_input()`, closing the preview gap with command registry metadata
- router migration phases are documented before execution behavior changes
- future router work should replace debug route duplication, add parity tests, introduce a handler registry, document the `shlex.split()` parser boundary, and make `chat_fallback_unprotected` visible before execution integration
- runtime slash and natural-language decoders remain future milestones

## Immediate Next Task

patch status fix is complete.

Observed behavior:

```bash
./agent-cli.py run --text "/patch status" --format json
# stdout is empty when repo is clean
```

Desired behavior:

```bash
./agent-cli.py run --text "/patch status"
# working tree clean
```

Status:

- `core.batch_runner._run_patch()` now delegates to `core.patch_frontdoor.run_patch_command()`.
- `agent-cli.py run --text "/patch status"` returns `working tree clean` on a clean repo.
- `agent-cli.py run --text "/patch status" --format json` returns the clean message in `stdout`.

## Current Codex State

codex inspect mode complete.

Verified commands:

- `./agent-cli.py run --text "/codex status"`
- `./agent-cli.py run --text "/codex prompt add /tree"`
- `./agent-cli.py run --text "/codex package add repo file search"`

## Current LLM State

/llm preset milestone started.

Inspect-only behavior:

- `./agent-cli.py run --text "/llm status"`
- `./agent-cli.py run --text "/llm preset coding"`
- `./agent-cli.py run --text "/llm preset general"`
- `./agent-cli.py run --text "/llm preset vision"`
- no automatic model downloads
- no automatic Ollama restarts
- no runtime mutation
- no automatic model switching

## Current LLM Apply State

/llm apply dry-run planning is started.

Inspect/planning-only behavior:

- `./agent-cli.py run --text "/llm apply coding --dry-run"`
- `./agent-cli.py run --text "/llm apply general --dry-run"`
- `./agent-cli.py run --text "/llm apply vision --dry-run"`
- no config mutation yet
- no automatic model downloads
- no automatic Ollama restarts
- next later milestone may add explicit config write with confirmation

## Current LLM Apply Write State

/llm apply write path is started.

Confirmed write behavior:

- `./agent-cli.py run --text "/llm apply coding --write --confirm"`
- `./agent-cli.py run --text "/llm apply general --write --confirm"`
- `./agent-cli.py run --text "/llm apply vision --write --confirm"`
- both `--write` and `--confirm` are required
- config file write only
- no automatic model downloads
- no automatic Ollama restarts
- no running session mutation beyond the config file write

## Current Web State

/web fetch/extract routing is started.

Inspect-only behavior:

- `./agent-cli.py run --text "/web fetch https://example.com"`
- `./agent-cli.py run --text "/web extract https://example.com"`
- `./agent-cli.py run --text "/search web example"`
- `./agent-cli.py run --text "/web search example"`
- `./agent-cli.py run --text "/web fetch https://example.com --cache"`
- `./agent-cli.py run --text "/web extract https://example.com --cache"`
- `./agent-cli.py run --text "/search web example --save"`
- no crawl behavior
- no browser execution
- no JavaScript execution
- search is bounded and inspect-only
- search does not automatically fetch result pages
- cache/report artifacts write locally under `reports/web-cache/`
- cache writes are inspect-only and do not enable replay or background indexing
- `core/scrape` owns reusable deterministic extraction logic
- `core/web.extractor` is a thin adapter over `core/scrape`
- output is bounded

## Current Repo Search State

Repo search now routes through `core/search`.

Inspect-only behavior:

- `./agent-cli.py run --text "/find README"`
- `./agent-cli.py run --text "/find patch_frontdoor"`
- `./agent-cli.py run --text "/search repo README"`
- no web search changes
- no crawl behavior
- no browser execution
- no JavaScript execution
- no vector behavior
- repo search is deterministic and repo-scoped
- `core/search` owns reusable repo-local search logic
- `/find` is a compatibility front door over `core/search`

## Current Ground State

The deterministic grounding layer now lives in `core/ground`.

Inspect-only behavior:

- `core/ground` owns reusable deterministic grounding evidence blocks
- grounding is bounded and line-window based
- `core/ground` does not search, mutate, execute, or plan
- `core/web.extractor` remains a compatibility adapter over `core/scrape`
- `core/scrape` continues to own reusable deterministic extraction logic
- `/ground repo <path>` is routed through `agent-cli.py`
- `/ground repo <path>` is inspect-only and repo-scoped
- `/ground collect <path> [path ...]` is routed through `agent-cli.py`
- `/ground collect <path> [path ...]` is inspect-only and repo-scoped
- `/ground search <query>` is routed through `agent-cli.py`
- `/ground search <query>` is inspect-only and repo-scoped
- `/ground reports` is routed through `agent-cli.py`
- `/ground show <report-id>` is routed through `agent-cli.py`
- `/ground reports` and `/ground show <report-id>` are inspect-only and inspect local grounding report artifacts
- `/ground ... --save` writes local reports under `reports/ground/`
- grounding reports are inspectable local artifacts; there is no replay or indexing path

## Current Response Policy State

`core/response_policy` has started as a deterministic runtime guard layer.

It detects:

- music/reference prompts
- full copyrighted lyrics requests
- display-lyrics requests
- ambiguous music entities
- reversed song/artist phrasing
- source-confirmation-needed cases

It returns decisions only.

It does not yet integrate into `agent.py` or `agent-cli.py`.

The next milestone is runtime integration into the live answer path without adding hidden autonomy.

## Current Runtime Pipeline Audit

The current live prompt pipeline, fallback risks, and target Typed Agent OS
boundary are documented in `docs/runtime-pipeline.md`.

The planned typed runtime input pipeline is documented in
`docs/runtime-router-redesign.md`.

The typed runtime input model layer currently lives in
`core/runtime_decoder/models.py`.

The deterministic slash-command decoder currently lives in
`core/runtime_decoder/slash.py`.

The current runtime risk areas are:

- direct chat fallback from `agent-cli.py` and from `core.agent_runtime`
- grounding gaps when a prompt is not classified as factual enough to use grounding
- unsupported synthesis when weak evidence reaches a chat synthesis step
- copyrighted output risk because `core.response_policy` is not wired into live dispatch yet

## Current Packaging Hardening State

`scripts/make_patch_package.py` now validates package completeness before writing ZIPs.

It fails loudly on relevant untracked files, rejects partial staged states, and records deterministic package metadata so false-success patch runs are blocked earlier.

`scripts/agent_patch_runner.py` now verifies the reconstructed git state after apply and before commit.

It checks that staged additions exist, staged modifications exist, staged deletions are absent, and the staged index matches the manifest exactly before commit.

New source/test/docs files must be staged explicitly.

## Next Milestone

Expand the AgentSpec MVP contract foundation carefully while keeping the existing deterministic runtime architecture explicit and bounded.

Reason:

- The current runtime is now broad enough that a contract layer should formalize front doors, artifacts, and safety stages.
- The deterministic inspect/plan/dry-run/approve/apply/report discipline is already established and should be documented as a contract.
- The grounding, search, web, and AgentSpec schema/rendering layers are stable enough to serve as the first contract-backed surfaces.

## Broader Roadmap

Next milestone:

1. Expand the AgentSpec MVP contract foundation with deterministic schema export, policy validation, decode, route, and dispatch-preview helpers, alongside schema, rendering, validation, and policy checks.
2. Keep `/web` cache/report follow-up verification bounded and keep cache replay out of scope.
3. Finish `/llm apply` config write follow-ups for Ollama preset application.
4. Keep repo-local search deterministic and repo-scoped through `core/search`.
5. Keep `/ground` inspection and report lookup deterministic, repo-scoped, and inspect-only through `core/ground`.
6. Ensure natural requests like `read README.md` and `read docs/` route locally.
7. Add Codex CLI execution after policy and model defaults are explicit.
8. Add project memory maintenance command or docs workflow.
