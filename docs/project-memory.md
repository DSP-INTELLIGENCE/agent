# Project Memory

This file is durable repo-local project memory for the agent project.

It should contain stable project facts, architectural decisions, and current handoff state.

Do not store secrets, personal credentials, API keys, private tokens, or temporary chat-only context here.

## Current Direction

The goal is to build a reusable local agent core that can support many kinds of agents.
Slash roots are the command system, and the command registry is the canonical slash-command catalog direction.

Core priorities:

- keep `core/` reusable and deterministic
- use `agent-cli.py` as the real terminal/batch front door
- treat legacy `agent.py` as deprecated until it is renamed/replaced later
- keep slash roots as the command system and `core/command_registry.py` as the canonical command metadata layer
- keep external CLI payloads outside the core repo where possible
- bind external capabilities through manifests, front doors, and policy
- let the agent help build itself only through reviewed patch packages

## Working Base

The current base has these working lanes:

- repo-local `.venv` bootstrap through `scripts/bootstrap_venv.sh`
- repo-local Python wrapper through `scripts/agent_python.sh`
- patch ZIP runner through `scripts/agent_patch_runner.py`
- patch ZIP builder through `scripts/make_patch_package.py`
- `/patch` front-door parser in `core/patch_frontdoor.py`
- `/patch` registration and dispatch in `core/agent_runtime.py`
- `/patch` batch routing in `core/batch_runner.py`
- `agent-cli.py run --text "/patch status"` works
- `agent-cli.py run --text "/patch dry-run ~/Downloads/foo.zip"` routes to the patch runner
- `/read`, `/ls`, `/tree`, and `/find` are repo-local front doors routed through `core.batch_runner`
- `/search repo <query>` and `/search web <query>` are routed through `core.batch_runner`
- `/web fetch`, `/web extract`, and `/web search` are routed through `core.batch_runner`
- `/ground repo`, `/ground collect`, `/ground search`, `/ground reports`, and `/ground show` are routed through `core.batch_runner`
- `/codex` inspect-only lane is complete
- `agent-cli.py` can run `/codex status`
- `agent-cli.py` can run `/codex prompt <task>`
- `agent-cli.py` can run `/codex package <task>`
- `/codex` currently prints constructed commands/prompts only and does not execute Codex
- `/codex` policy is inspect-only until an explicit later execution milestone
- `/llm` preset milestone is started
- `agent-cli.py` can run `/llm status`
- `agent-cli.py` can run `/llm preset coding`
- `agent-cli.py` can run `/llm preset general`
- `agent-cli.py` can run `/llm preset vision`
- `/llm apply` dry-run planning is started
- `agent-cli.py` can run `/llm apply coding --dry-run`
- `agent-cli.py` can run `/llm apply general --dry-run`
- `agent-cli.py` can run `/llm apply vision --dry-run`
- `/llm apply` config write path is started
- `agent-cli.py` can run `/llm apply coding --write --confirm`
- `agent-cli.py` can run `/llm apply general --write --confirm`
- `agent-cli.py` can run `/llm apply vision --write --confirm`
- `/llm` currently prints inspect/configuration text only and does not download models, restart Ollama, or mutate runtime state automatically
- `/llm apply` currently prints dry-run plans or writes a local preset config file only when both `--write` and `--confirm` are supplied
- `/llm apply` does not download models or restart Ollama
- `/web fetch` and `/web extract` are routed through `agent-cli.py`
- `/search web <query>` and `/web search <query>` are routed through `agent-cli.py`
- `/web fetch <url> --cache`, `/web extract <url> --cache`, and `/search web <query> --save` are routed through `agent-cli.py`
- `/web` currently supports fetch/extract/search only; there is still no crawl, browser, or JavaScript execution
- `/web` output is bounded
- `/search` output is bounded and does not fetch result pages automatically
- `/web` cache/report artifacts write to `reports/web-cache/`
- `/web` cache writes are inspect-only and write-only; there is no automatic cache replay or background indexing
- `core/scrape` now owns reusable deterministic extraction logic
- `core/web.extractor` is now a thin adapter over `core/scrape`
- `core/search` now owns reusable deterministic repo-local search logic
- `/find` is a compatibility front door over `core/search`
- `/search repo <query>` is routed through `agent-cli.py`
- no web/crawl/vector behavior was added for repo search
- `core/ground` now owns reusable deterministic grounding evidence blocks
- `core/ground` is pure extraction and normalization only; it does not search, mutate, execute, or plan
- `core/ground.store` provides deterministic report lookup helpers for saved local grounding reports
- `/ground repo <path>` routes through `agent-cli.py`
- `/ground repo <path>` is inspect-only and exposes bounded grounded excerpts from `core/ground`
- `/ground collect <path> [path ...]` routes through `agent-cli.py`
- `/ground collect <path> [path ...]` is inspect-only and aggregates bounded grounded excerpts from explicit repo-local paths only
- `/ground search <query>` routes through `agent-cli.py`
- `/ground search <query>` is inspect-only and composes repo search with grounded evidence blocks
- `/ground reports` routes through `agent-cli.py`
- `/ground show <report-id>` routes through `agent-cli.py`
- `/ground reports` and `/ground show <report-id>` are inspect-only and inspect local grounding report artifacts without replay or execution
- `/ground ... --save` writes local reports under `reports/ground/`
- grounding reports are inspectable local artifacts; there is no replay or indexing path
- `data_agent/` is legacy and remains in place for now; the retirement plan documents the staged path to a command-registry-centric layout
- `data/commands/` fixture schema has started as the future canonical slash-command catalog metadata layer
- do not delete or move `data_agent/` yet
- `core/command_registry_loader.py` loads `data/commands` fixtures as deterministic metadata only
- do not integrate runtime behavior yet
- `core/response_policy` is a deterministic runtime guard layer for factual/reference prompts
- `core/response_policy` detects music/reference prompts, full lyrics requests, display-lyrics requests, ambiguous music entities, reversed song/artist phrasing, and source-confirmation-needed cases
- full copyrighted lyrics requests are refused by the guard layer
- unresolved music entities clarify instead of hallucinating a factual answer
- `core/response_policy` returns decisions only; it is not yet wired into `agent.py` or `agent-cli.py`
- Codex prompts should be short by default; use giant prompts only for dangerous architecture changes
- report/cache artifact lanes are local filesystem only:
  - `reports/web-cache/`
  - `reports/ground/`
  - `reports/patch-runs/`
- patch packaging now validates staged/untracked completeness before building ZIPs
- patch packaging now emits deterministic package metadata and blocks false-success partial commits
- new source/test/docs files must be explicitly staged before packaging
- patch runner now validates reconstructed git state before commit
- staged additions, modifications, and deletions must survive the apply-to-commit lifecycle
- package manifest enforcement happens after apply and before commit
- docs/runtime-pipeline.md now records the live prompt flow, direct fallback points, and the Typed Agent OS boundary
- docs/runtime-router-redesign.md now records the planned typed runtime input pipeline and spec boundary
- docs/runtime-router-audit-roadmap.md records the phased router migration roadmap
- response_policy runtime integration remains a future milestone
- AgentSpec is not executable; AgentScript is the future executable artifact
- response_policy decides, but does not answer
- grounding produces evidence, not guesses
- runner executes only explicit approved AgentScript commands
- no hidden autonomy rule: inspect, plan, dry-run, approve, apply, and report remain distinct
- raw prompt routing is being redesigned toward typed input specs before runtime behavior changes
- runtime_decoder InputSpec models are started in `core/runtime_decoder/models.py`
- deterministic slash command decoding is started in `core/runtime_decoder/slash.py`
- slash decoder root matching is case-insensitive while preserving user-visible command and argument casing
- slash decoder now covers live command families like `/help`, `/commands`, `/state`, `/config`, `/fs`, `/python`, `/shell`, `/remember`, `/memory`, and `/plugin*`
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
- `docs/data-agent-retirement-plan.md` records the staged path for retiring legacy `data_agent/` abstractions
- `core/command_registry.py` now provides the dependency-free command registry schema and default fixtures only
- `data/commands/` is the future canonical slash-command catalog fixture layer
- command registry lookup and construction are inspect-only metadata helpers; no execution or handler calls were added
- `core/execution_dispatch.py` now provides inspect-only registry-backed execution dispatch scaffolding and dispatch plans
- `core/execution_dispatch_render.py` renders dispatch plans deterministically as inspect-only JSON and markdown
- dispatch-plan parity coverage now compares registry-backed plans against command registry metadata before execution integration
- `core.batch_runner` now uses registry-backed dispatch planning for the read-only repo surfaces `/read`, `/ls`, `/tree`, and `/find` while preserving behavior
- slash roots remain the canonical command surfaces; `/web`, `/llm`, `/vision`, and `/image` are treated as first-class dispatch families in metadata-only scaffolding
- handler registry/execution integration remains future work
- slash roots are the command system; the command registry is the canonical slash-command catalog direction
- `/switch`, `/tool`, plugin language, tool gateway language, and switch matrix language are legacy compatibility only
- `/web`, `/search`, `/llm`, `/git`, `/grep`, `/ls`, `/tree`, `/find`, `/python`, `/shell`, `/firefox`, `/ground`, and `/patch` are first-class slash-root command surfaces
- slash roots are first-class command surfaces and the `data/commands` fixtures are the future canonical catalog layer
- `docs/render` is an inspect-only registry docs rendering surface in the command registry schema
- `core/command_registry_render.py` renders registry metadata deterministically as inspect-only JSON and markdown
- command registry route parity tests now compare typed `RouteDecision` preview modes against registry metadata before execution integration
- `/commands` now previews as the help route in `route_runtime_input()`, closing the preview gap with command registry metadata
- future router work should replace debug route duplication, add parity tests, introduce a handler registry, document the `shlex.split()` parser boundary, and make `chat_fallback_unprotected` visible before execution integration
- runtime slash and natural-language decoders remain future milestones
- there are no `core/llm/` or `core/codex/` packages yet; those front doors live in `core/llm_frontdoor.py` and `core/codex_frontdoor.py`
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

## Patch Workflow

Preferred workflow:

```text
assistant creates patch ZIP
user downloads ZIP to ~/Downloads
agent-cli.py or scripts/agent_patch_runner.py validates/applies it
patch runner creates reports under reports/patch-runs/
git records accepted changes
```

Stable direct invocation:

```bash
./scripts/agent_python.sh scripts/agent_patch_runner.py <patch.zip> --dry-run
./scripts/agent_python.sh scripts/agent_patch_runner.py <patch.zip> --commit "message" --push
```

Stable CLI invocation:

```bash
./agent-cli.py run --text "/patch status"
./agent-cli.py run --text "/patch dry-run ~/Downloads/foo.zip"
```

## Current Known Issue

`/patch status` through `agent-cli.py` currently routes correctly but may return empty stdout when the working tree is clean.

The intended fix is to make `core.batch_runner._run_patch()` delegate to `core.patch_frontdoor.run_patch_command()` so it inherits the visible clean message from the patch front door.

Expected outcome:

```bash
./agent-cli.py run --text "/patch status"
# working tree clean
```

## Near-Term Goals

Keep the live prompt pipeline explicit in `docs/runtime-pipeline.md` before changing runtime behavior.
Keep the planned typed runtime input pipeline explicit in `docs/runtime-router-redesign.md` before changing runtime behavior.
Keep `core/runtime_decoder` as the typed input model layer before adding parsing or routing.
Keep deterministic slash decoding narrow and non-executing.

1. Keep the deterministic runtime architecture explicit and documented rather than hidden behind autonomous behavior.
2. Keep `core/response_policy` on deck for runtime integration as the next guard milestone, while keeping it deterministic and inspectable.
3. Keep patch packaging hardened so staged/untracked completeness is validated before ZIP build.
4. Keep patch runner reconstructed-state validation in place so staged additions survive apply-to-commit.
5. Move toward an AgentSpec MVP contract foundation with deterministic schema export, policy validation, decode, route, and dispatch-preview helpers.
6. Keep `/llm apply` config write follow-ups explicit and safety-gated.
7. Keep repo-local file/document front doors deterministic and repo-scoped.
8. Keep `/web` search inspect-only and bounded; no automatic result fetching or crawling.
9. Keep `/web` cache/report artifacts write-only and local; no automatic cache replay or background indexing.
10. Keep `/find` and `/search repo` deterministic and repo-scoped through `core/search`.
11. Keep Codex CLI execution out of chat until the model/provider lanes are explicit.
12. Keep building through patch ZIPs, not manual repo edits.
13. Keep the grounding layer deterministic and bounded through `core/ground`.
14. Keep `/ground repo <path>` inspect-only and repo-scoped.
15. Keep `/ground collect <path> [path ...]` inspect-only and repo-scoped.
16. Keep `/ground search <query>` inspect-only and repo-scoped.
17. Keep grounding reports inspectable and local under `reports/ground/`.
18. Keep report/cache artifact lanes local and deterministic.

## Design Rules

- LLMs may propose changes.
- Patch packages carry changes.
- Patch runner validates and applies changes.
- Git records accepted changes.
- The patch runner remains the final policy gate.
- No hidden autonomy: inspect, plan, dry-run, approve, apply, and report are distinct stages.
- No direct arbitrary shell execution from chat.
- No auto-push unless explicitly requested.
- No secrets in repo memory.

## Useful Commands

```bash
git status --short
git log --oneline -5
./scripts/agent_python.sh -m py_compile core/patch_frontdoor.py
./scripts/agent_python.sh -m py_compile core/batch_runner.py
./agent-cli.py run --text "/patch status" --format json
```
