# Endpoints and Decoders

## Definition

Endpoints are final decoders or execution targets.

Examples:

```text
Ollama local models
Codex CLI
Open WebUI
ChatGPT
OpenAI API
OpenRouter
custom HTTP APIs
local tools
```

## LLM endpoints

LLM endpoints can be local or remote.

Examples:

```text
/llama3:8b prompt hello
/qwen2.5-coder:14b ground write python code
/codex prompt inspect this repo
```

## Ollama endpoints

Ollama endpoints are populated from `ollama list`.

Example source list:

```text
dolphincoder:7b
gpt-oss:20b
qwen3:14b
qwen2.5-coder:14b
qwen3:8b
qwen2.5vl:7b
llama3:8b
llama3.1:8b
codellama:7b
codegemma:7b
```

The exact list is machine-specific and should be discovered at runtime or cached in config.

## Codex endpoint

Codex CLI can be an endpoint for repo-aware operations.

A Codex endpoint may expose configuration such as:

```text
profile
sandbox mode
network access
approval policy
writable roots
```

Example conceptual command:

```text
/codex --profile or-codex --sandbox workspace-write --approval on-request
```

## Endpoint contract

An endpoint should declare:

```text
name
type
availability check
input format
output format
capabilities
limits
requires network
requires filesystem
requires approvals
```

## Endpoint routing

Endpoints can be selected by lane defaults or explicit endpoint-qualified invocation:

```text
/<endpoint> <lane> <input>
```

The endpoint selection layer should not hard-code model names. It should read configured endpoints and/or discovered endpoints.
