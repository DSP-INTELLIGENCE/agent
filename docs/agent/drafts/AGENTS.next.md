# Agent Operator Instructions

Architecture contract:

```text
/prompt = direct base LLM lane
/ground = grounded/RAG answer lane
/summon = persona/session control and explicit /summon prompt
```

Patch discipline:

```text
review -> inspect report -> publish -> merge-cleanup
```

Never publish before review. Never apply directly on `main`. Never use heredocs for patching.

Grounding target:

```text
GroundingQuery -> GroundingService/providers -> EvidencePacket -> LLM synthesis
```

Codec target:

```text
codec prompt -> /prompt
codec ground -> /ground
codec patch -> canonical patch engine
```
