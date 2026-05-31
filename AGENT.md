Yes — write it as an **architecture overview**, not operational patch instructions. Something like this:

````markdown
# Agent Architecture Overview

`agent` is a configurable command and routing layer for working with model endpoints, adapters, filters, and semantic controllers.

The repo should separate these concerns:

1. lanes / routes
2. filters / adapters
3. endpoints
4. semantic controllers
5. frontend tools

## Agent

The agent is responsible for routing input to configured lanes and endpoints.

The agent does not need to define every semantic controller, model, or adapter internally. It only needs a stable contract for connecting to them.

Core responsibilities:

1. expose lanes and routes
2. connect lanes to adapters or endpoints
3. allow adapters to be chained
4. route prompts to model endpoints
5. support local and external LLM runtimes
6. keep repo docs, patch workflow, and runtime behavior aligned

## Semantic Controllers

Semantic controllers sit outside the core agent.

They connect user intent to lanes and may use external semantic routing tools such as:

1. `semantic-router`
2. sentence transformers
3. embedding models
4. configured route definitions
5. external controller services

Semantic controllers are not defined by `agent` itself.

The agent only needs to know how to receive the selected lane or route.

Example flow:

```text
user input
  -> semantic controller
  -> selected lane
  -> adapters / filters
  -> endpoint
  -> response
````

## Lanes

A lane is a named route into a behavior path.

Lanes can connect directly to endpoints or pass through adapters and filters first.

Lanes are configurable.

A lane may define:

1. name
2. route prefix
3. semantic description
4. adapter chain
5. endpoint target
6. fallback behavior

Examples:

```text
/prompt
/ground
/web
/summon
/patch
/codex
/llm
```

A lane may also be model-addressed:

```text
/<model> <lane> <input>
```

Examples:

```text
/llama3:8b prompt hello
/qwen2.5-coder:14b ground write python code
/codex patch inspect this repo
```

Lanes may be connected to semantic controllers, but the semantic controller definitions live outside the core agent.

## Routes

Routes are the concrete command names or prefixes used to enter lanes.

A route can be explicit:

```text
/ground explain this file
/web search this topic
/prompt write a summary
```

Or model-prefixed:

```text
/qwen3:14b prompt summarize this
/llama3:8b ground answer with evidence
```

Routes should be configurable instead of hard-coded wherever possible.

## Adapters

Adapters are plugins, filters, or processing layers that can be attached to lanes.

Adapters can be chained.

Examples:

1. ground
2. web
3. RAG
4. AI
5. browser
6. patcher
7. formatter
8. safety filter
9. repo inspector
10. response normalizer

Example adapter chain:

```text
/ground
  -> document lookup
  -> evidence filter
  -> synthesis adapter
  -> LLM endpoint
```

Adapters can be created for any behavior as long as they obey the lane contract.

## Endpoints

Endpoints are execution targets.

An endpoint may be:

1. an Ollama model
2. Codex CLI
3. Open WebUI
4. ChatGPT
5. OpenAI API
6. OpenRouter
7. another local or remote model runtime

Endpoints should be configurable.

The agent should not assume only one backend exists.

## LLM Endpoints

LLM model endpoints may be populated from:

```bash
ollama list
```

Example local model list:

```text
dolphincoder:7b
gpt-oss:20b
qwen3:14b
qwen2.5-coder:14b
qwen2.5-coder:7b
qwen2.5-coder:3b
qwen3:8b
qwen3:4b
llama3:8b
llama3.1:8b
llama3.2:3b
codellama:7b
codegemma:7b
gemma3:4b
hermes3:8b
nous-hermes:7b
```

Model-addressed command shape:

```text
/<model> <lane> <input>
```

Examples:

```text
/llama3:8b prompt hello
/qwen2.5-coder:14b ground write python code
/qwen3:14b summarize this document
```

## Codex Endpoint

Codex can be treated as an endpoint or specialized lane.

Example shape:

```text
/codex <task> [options]
```

Possible options:

```text
--profile <profile>
--sandbox <mode>
--accept <mode>
```

Example:

```text
/codex patch --profile repo --sandbox allow-write --accept request
```

Codex should be handled as a configurable execution endpoint, not hard-coded into unrelated lanes.

## Generic Command Shape

The general command shape is:

```text
/<lane> <adapters-or-filters> <input>
```

Or:

```text
/<model> <lane> <input>
```

Examples:

```text
/ground rag explain this repo
/web search latest docs
/prompt write a README
/llama3:8b prompt hello
/qwen2.5-coder:14b ground inspect this code
```

## Codec

`codec` is the frontend tool for agent-oriented workflows.

It may provide:

1. agent frontend commands
2. patch workflow commands
3. repo inspection commands
4. status reporting
5. patch packaging helpers

`codec` should be documented as a frontend tool, not confused with the core agent runtime.

## agent.py

`agent.py` is a legacy terminal entrypoint.

It should remain documented only as legacy compatibility unless it is promoted again.

## agent-cli.py

`agent-cli.py` is a legacy CLI entrypoint.

It should remain documented only as legacy compatibility unless it is promoted again.

## Design Rule

The repo should avoid mixing these layers:

```text
semantic controller != lane
lane != adapter
adapter != endpoint
frontend tool != runtime
legacy CLI != canonical architecture
```

The active docs should always state which layer a file or command belongs to.

```
```
