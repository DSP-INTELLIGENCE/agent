# Legacy semantic stack

The semantic router, AgentSpec, AgentScript, and encoder layers are legacy/archive-only.

They must not:

- authorize runtime lanes
- select routes for execution
- execute commands
- call the LLM
- call grounding, web, scrape, or repository tools
- act as aliases for `/prompt`, `/ground`, or `/summon`

The only active user-facing LLM lanes are:

- `/prompt` for direct base-model prompting
- `/ground` for grounded/RAG answers after evidence collection
- `/summon` for persona/session control and explicit `/summon prompt <message>` prompting

Future grounding work should target the `/ground` EvidencePacket/provider-adapter pipeline directly. Do not rebuild semantic routing as the runtime front door.
