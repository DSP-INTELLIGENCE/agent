# Core LLM lanes

Agent has exactly three user-facing lanes that may call the LLM.

| Lane | Purpose | Contract |
| --- | --- | --- |
| `/prompt` | Direct base LLM prompt | Sends only the user message to the base model. It does not implicitly ground, search, scrape, fetch, or use summoned personas. |
| `/ground` | Grounded/RAG answer | Builds evidence first, stores the grounding state, then sends the grounded evidence context to the LLM for final synthesis. |
| `/summon` | Persona/session control and explicit persona prompting | Manages summoned persona state. Persona-routed LLM work enters only through `/summon prompt <message>`. |

Everything else that previously looked like an answer lane is legacy and unwired. Do not alias those old command names to the current lanes.

Inspection and support surfaces such as `/grounding`, `/sources`, repository commands, patch commands, web/search/scrape tools, and route diagnostics are not additional LLM lanes.
