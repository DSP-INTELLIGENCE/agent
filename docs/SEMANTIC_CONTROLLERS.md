# Semantic Controllers

## Definition

Semantic Controllers connect user intent to Agent lanes.

They are external to Agent.

They may use:

```text
semantic-router
sentence transformers
embedding models
classifier models
rules
hybrid routing
```

## Boundary

Agent should not need to know how a Semantic Controller works internally.

Agent only needs to accept a selected lane or route decision.

```text
Semantic Controller:
  user input -> lane decision

Agent:
  lane decision -> adapters -> endpoint
```

## Why external

Keeping Semantic Controllers external avoids coupling Agent runtime to:

```text
semantic-router dependency versions
sentence-transformer models
embedding stores
model-specific classifier behavior
training data
routing experiments
```

## Config binding

A Semantic Controller can be bound to lanes by config.

Example conceptual binding:

```text
controller: repo-intent-router
lanes:
  prompt
  ground
  web
  rag
```

## Non-goal

This document does not reactivate legacy semantic-router runtime execution inside Agent. It defines the boundary for future external controller integration.
