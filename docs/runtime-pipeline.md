# Runtime Prompt Pipeline

This document audits the current live prompt flow and the places where unsafe
direct fallback can enter before any future runtime behavior changes.

## Current Flow

### Batch front door

`agent-cli.py` routes non-interactive input through `core.batch_runner.run_command()`.

Current order for slash-surface handling is:

1. `/switch`
2. `/tool`
3. `/llm`
4. `/codex`
5. `/search`
6. `/web`
7. repo-local front doors such as `/read`, `/ls`, `/tree`, `/find`, and `/ground ...`
8. `/patch`

If the input does not match a handled slash surface, `core.batch_runner` falls
back to `_run_chat()`, which sends the raw prompt to the configured chat
provider. That is a direct assistant fallback path.

### Interactive runtime

`agent.py` is only a thin wrapper around `core.main.main()`, which launches the
live interactive runtime in `core.agent_runtime`.

The interactive path is:

1. `agent.py`
2. `core.main.main()`
3. `AgentPlainCli` or `AgentTuiApp`
4. `AgentCore.handle_input()`
5. `RequestRouter.route()`
6. `SharedPlanner.plan()`
7. `SharedDispatcher.dispatch()`

Within `RequestRouter.route()`, the current order is:

1. exact slash command parsing
2. deterministic natural-language command parsing
3. fallback routing

The fallback router can still send input to:

- `chat.reply`
- `chat.grounded_reply`
- `web.search`
- `web.fetch`
- `memory.retrieve`
- other explicit tool/system paths

That means a prompt can become direct chat synthesis if the heuristics do not
classify it as a factual lookup, web request, or other explicit route.

## Grounding Path

The factual-answer path in `core.agent_runtime` is `chat.grounded_reply`.

Current behavior:

- `evaluate_grounding_request()` builds a grounding guard
- Wikipedia is tried first
- if needed, multi-source web fallback is collected
- `grounding_supports_answer()` decides whether the gathered evidence is strong enough
- weak or missing evidence returns a refusal-style message instead of a grounded answer
- successful grounding still ends in model synthesis from the gathered evidence
- `clean_internal_prompt_leak()` strips obvious prompt leakage from the final text

This is evidence-gated synthesis, not a proof system.

## Web Path

The explicit and fallback web paths are currently separate from repo search and
grounding evidence.

Current web behavior:

- `/web fetch` and `/web extract` go through the deterministic core web fetch/extract layers
- `/web search` and `/search web` go through deterministic DDGS-backed search
- results are bounded and do not automatically fetch follow-up pages
- cache/report writes go under `reports/web-cache/`
- no browser automation, JavaScript execution, or crawl graph exists in this layer

## Ground Artifact Path

Grounding reports and lookups are local artifacts only:

- `/ground repo <path>`
- `/ground collect <path> [path ...]`
- `/ground search <query>`
- `/ground reports`
- `/ground show <report-id>`
- `/ground ... --save`

Artifacts are written under `reports/ground/`.
There is no replay path, no automatic indexing, and no autonomous re-grounding.

## Current Policy Coverage

There is no live `core.response_policy` integration yet.

Current guards in the live runtime are limited to:

- route heuristics
- grounding acceptance checks
- prompt leak cleanup
- local chat prompt validation

The deterministic `core.response_policy` package already exists, but the live
agent does not consult it yet.

## Current Risks

The main current risks are:

- direct chat fallback can bypass grounding and answer policy
- hallucinations can enter through `chat.reply`
- unsupported synthesis can enter through `chat.grounded_reply` when evidence is weak or misread
- copyrighted output risks exist because the live runtime does not yet consult `core.response_policy`
- entity ambiguity can slip through route heuristics
- sensitive biographical claims need stronger grounding than the current heuristic gate guarantees
- grounding failure can still lead to direct synthesis when the router misclassifies the prompt as normal chat

## Target Typed Agent OS Flow

The intended target architecture is:

- Frontend interacts.
- Spec describes.
- Policy gates.
- Grounding proves.
- Compiler emits.
- Runtime executes.
- Artifacts record.

The permanent boundaries are:

- AgentSpec is not executable.
- AgentScript is executable.
- agentspec never executes.
- core/compiler never executes.
- response_policy decides, but does not answer.
- grounding produces evidence, not guesses.
- runner executes only explicit approved AgentScript commands.
- no hidden autonomy rule: inspect, plan, dry-run, approve, apply, and report remain distinct.

## Phase Notes

The later platform phases remain:

- OS integration is later Phase 8.
- Application integration is later Phase 9.
- Cross-platform runtime is later Phase 10.

