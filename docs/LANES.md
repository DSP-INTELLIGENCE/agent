# Lanes and Routes

## Definition

A lane is a named switch or route that receives user input and sends it through a configured path.

A route is the concrete mapping from a lane name to adapters and endpoints.

```text
/<lane> <input>
```

or, for endpoint-qualified invocation:

```text
/<endpoint> <lane> <input>
```

## Examples

```text
/prompt hello
/ground what changed?
/web find current docs
```

Future endpoint-qualified examples:

```text
/llama3:8b prompt hello
/qwen2.5-coder:14b ground write python code
/codex prompt inspect this repo
```

## Responsibilities

A lane may define:

```text
name
aliases
semantics
adapter chain
default endpoint
allowed endpoints
controller binding
```

## Semantic-controller binding

A lane can be connected to a Semantic Controller, but Agent should not need to define the controller internals.

The controller may decide:

```text
user intent -> lane
```

Agent executes:

```text
lane -> adapters -> endpoint
```

## Built-in semantics

The first-class built-in semantics are:

```text
prompt
ground
summon
```

These remain stable even as lane names and routes become configurable.

## Configurable names

Lane names and `/switch` names should be configurable. A deployment can choose names and aliases that make sense for its environment.

Examples:

```text
ground -> evidence-backed answer lane
web -> web/search adapter lane
rag -> retrieval adapter chain
research -> multi-adapter research chain
```

## Non-goals

This document does not define semantic-router internals, sentence-transformer models, embedding storage, endpoint execution, or adapter execution.
