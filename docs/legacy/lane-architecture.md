# Lane architecture

The runtime uses explicit lanes. Plain text is not sent to the model. A command must enter one of the approved LLM lanes before synthesis can happen.

## LLM lanes

### `/prompt`

Direct base LLM lane. It receives the user message and does not add grounding evidence, search results, scraped pages, repository context, or summoned persona state unless a future explicit contract says otherwise.

### `/ground`

Grounded/RAG lane. It is the only grounded answer lane. It should normalize the user query, collect evidence, store the last grounding packet/state, and then send the evidence context to the LLM for final answer synthesis.

`/grounding` and `/sources` inspect the last grounded/evidence run. They are diagnostics, not separate answer lanes.

### `/summon`

Persona/session control. Persona-routed LLM work is explicit through `/summon prompt <message>`. Summoned personas must not silently take over `/prompt` or `/ground`.

## Legacy command policy

Old answer-like prompt-template command names are unwired. They must be rejected rather than aliased. New provider, RAG, or synthesis work should target `/ground` and the EvidencePacket/provider-adapter pipeline.

## Support surfaces

Search, web, scrape, repository, patch, route, and diagnostic commands may gather or display context, but they are not LLM answer lanes unless routed through one of the three approved lanes above.
