# LLM Control Plane

LLM behavior is a domain front door, not the whole agent.

## Front door

```text
/llm
/ai
```

Both should resolve through the same switch and provider policy path before any provider call.

## Flow

```text
LLM request
  -> llm front door
  -> switch resolve for llm capability
  -> provider/model selection
  -> provider adapter
  -> normalized response envelope
```

## Provider config

Provider configuration should stay explicit. Environment variables and provider defaults should be read by provider config modules, not scattered throughout the runtime.

## Model selection

Model selection should be represented as state:

```text
provider
model
backend
chat target
```

The runtime should be able to inspect the selected state without making a chat call.

## Grounding

Grounding is a separate factual-safety layer. It should decide when claims require sources, when evidence is weak, and when the agent should refuse or correct itself.
