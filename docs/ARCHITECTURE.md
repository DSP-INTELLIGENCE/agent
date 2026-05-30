# Agent Architecture

## Purpose

Agent is the runtime and operator surface for configurable AI work. The architecture is organized around three concepts:

1. **Lanes / Routes**
2. **Filters / Adapters**
3. **Endpoints / Decoders**

The Agent repository should own the runtime-facing contract for these concepts, while semantic controller internals can live outside Agent.

## Core model

```text
input
  -> lane / route
  -> adapter chain
  -> endpoint / decoder
  -> response
```

A lane is a named switch. A lane may have semantics, but it should not need to embed the semantic-controller implementation.

An adapter is a filter, plugin, provider, tool, or transformation that can run before or after an endpoint.

An endpoint is the final decoder or execution target. Examples include local Ollama models, Codex CLI, Open WebUI, ChatGPT, the OpenAI API, OpenRouter, or other configured backends.

## Semantic Controllers

Semantic Controllers connect natural-language or semantic intent to lanes. They may use semantic-router, sentence transformers, embeddings, classifier models, or other controller logic.

Semantic Controllers are defined outside Agent. Agent does not need to own their internal model, training data, embedding stack, or routing implementation.

Agent only needs the contract:

```text
semantic controller chooses or suggests a lane
agent executes the configured lane
```

## Built-in lane semantics

The currently important built-in lane semantics are:

```text
prompt
ground
summon
```

These are semantics, not a limit on future configurable lane names.

A deployment may configure additional lanes such as:

```text
web
rag
research
tool
```

Those should be configured as lanes, aliases, or adapter chains rather than revived as hard-coded legacy runtime paths.

## Legacy distinction

Legacy terms such as `/question`, `/rag`, and `/research` should not be reintroduced as hard-coded runtime paths. They may exist as configured aliases or adapter-chain names if a deployment explicitly defines them.

## Codec

`codec.py` is the clean frontend for Agent. It should hide legacy invocation clutter and expose clear operator commands.

`codec-patch.py` is the staged patch operator.

`agent.py` is the legacy terminal surface.

`agent-cli.py` is the legacy CLI/batch compatibility surface.
