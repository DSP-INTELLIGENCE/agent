# Runtime boundaries

Agent separates routing, context assembly, evidence building, and final LLM synthesis.

## LLM boundary

Only three user-facing lanes may reach the LLM:

- `/prompt` for direct base-model prompting.
- `/ground` for grounded/RAG answers after evidence collection.
- `/summon` for persona/session control, with persona-routed prompting through `/summon prompt <message>`.

Plain text and legacy answer-like command names do not cross the LLM boundary. They should return validation errors.

## Grounding boundary

`/ground` owns the grounding path. It must build evidence before final answer synthesis. `/grounding` and `/sources` expose the latest evidence state for inspection only.

## Support boundary

Repository, search, web, scrape, route, and patch commands are support surfaces. They may collect data or inspect state, but they do not become LLM lanes on their own.

<!-- agent-legacy-semantic-stack:start -->
## Legacy semantic stack boundary

Semantic router, AgentSpec, AgentScript, and encoder layers are legacy/archive-only. They do not cross the runtime boundary and must not authorize, select, or execute lanes.
<!-- agent-legacy-semantic-stack:end -->
