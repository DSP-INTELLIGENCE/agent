Agent architecture rules:

Agent is an AI-native terminal runtime.

Core law:
instruction -> lane -> runtime/search/ground/scrape -> assemble -> LLM -> response

Routing rules:
- Nothing goes to the LLM without an explicit lane.
- /prompt is direct raw LLM lane.
- /web is web/search lane.
- /scrape is scrape lane.
- /ground is grounding diagnostics/evidence lane.
- /ground exposes grounding.

Boundaries:
- CommandRegistry is canonical lane metadata.
- Semantic router may choose a lane, but does not execute.
- Lane registry validates selected lane.
- LLM is final response composer, not router and not evidence source.
- No plugins.
- No tools abstraction.
- No switch matrix.
- agent.py is legacy unless explicitly scoped.
- agent-cli.py is canonical command-line frontend.

Prompt style:
- Use short prompts by default.
- Use large prompts only for dangerous architecture changes.
- Prefer code + tests.
- Avoid docs unless explicitly requested.

Current pivot:
- `agent-cli.py` is the backend execution boundary, not merely a frontend.
- Semantic routing and encoder layers are frontend-only.
- Encoders may propose explicit `agent-cli.py` backend requests or packet requests.
- Encoders do not execute, fetch, search, mutate, call tools, call the LLM, or bypass validation.
- `RouteDecision` is inspect-only and never authorizes answering or execution.
- Plain text fallback must not route into semantic route execution.
- Decoder/final response must summarize validated backend packets only.
- Live terminal wiring is paused until AgentSpec, AgentScript, validation, capability checks, and evidence packet boundaries are complete.

Patch operator rules:
- Patch ZIPs use the staged workflow package format.
- One command = one stage = stop.
- Codex is a patch-stage runner only unless explicitly told otherwise.
- Codex must not manually edit files or invent changes.
- Use staged package scripts for inspect, preflight, apply, test, report, commit, and push.
- Do not run live LLM/Ollama checks unless `requires_live_llm` is true and the user explicitly approves.

<!-- agent-three-llm-lanes:start -->
LLM lane contract:

- `/prompt` is the direct base LLM lane. It must not implicitly ground or use summoned personas.
- `/ground` is the grounded/RAG lane and must build evidence before final LLM synthesis.
- `/summon` is persona/session control; `/summon prompt <message>` is the explicit persona-routed prompt path.
- Old answer-like prompt template command names are legacy and unwired. Do not alias them to current lanes.
- `/grounding`, `/sources`, repo commands, patch commands, and tool/web support commands are inspection/support surfaces, not additional LLM lanes.
<!-- agent-three-llm-lanes:end -->

<!-- agent-grounded-resolver-memory:start -->
## Grounded resolver memory

Current lane policy:

- `/prompt` stays direct-to-LLM. Do not route it through `/ground` or summon personas implicitly.
- `/ground` is the primary grounded/RAG lane and the evidence-builder surface.
- Old answer-like command names are unwired and must not become aliases.
- `/summon` manages persona/session state; `/summon prompt <message>` is the explicit persona prompt path.
- Do not add additional grounded lane names.

Checked:

- [x] resolver normalizes boilerplate commands before lookup
- [x] song-author query normalization keeps song disambiguators
- [x] source scorer rejects embedded-title false positives
- [x] short ambiguous location queries can stop before random grounding

Unchecked:

- [ ] structured EvidencePacket
- [ ] provider adapters
- [ ] optional real grounding packages behind fallbacks
<!-- agent-grounded-resolver-memory:end -->

<!-- agent-legacy-semantic-stack:start -->
Semantic stack policy:

- Treat semantic router, AgentSpec, AgentScript, and encoder layers as legacy/archive-only.
- Do not route runtime work through them.
- Do not use them to authorize lanes, select lanes, or call the LLM.
- Do not add aliases from old semantic/plan/route surfaces to `/prompt`, `/ground`, or `/summon`.
- Build future grounding work directly behind `/ground` using EvidencePacket/provider adapters.
<!-- agent-legacy-semantic-stack:end -->
