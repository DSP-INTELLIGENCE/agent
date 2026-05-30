# Adapters and Filters

## Definition

Adapters are chainable filters, plugins, providers, tools, or transformations.

They can be placed before an endpoint, after an endpoint, or around a lane.

```text
lane -> adapter -> adapter -> endpoint
```

## Adapter examples

```text
ground
web
rag
ai
search
scrape
read
tool
custom plugin
```

## Adapter responsibilities

An adapter may:

```text
normalize input
fetch evidence
retrieve documents
call a tool
read files
query web/search
transform prompts
filter unsafe or invalid operations
format endpoint context
validate output
attach metadata
```

## Chain examples

Grounded answer:

```text
ground lane
  -> query normalization adapter
  -> evidence adapter
  -> citation/evidence packet adapter
  -> endpoint
```

Web answer:

```text
web lane
  -> search adapter
  -> scrape/read adapter
  -> summarization adapter
  -> endpoint
```

RAG answer:

```text
rag lane
  -> retrieval adapter
  -> rerank adapter
  -> context builder adapter
  -> endpoint
```

## Legacy mapping

`/rag` and `/research` should be treated as adapter-chain configurations or lane aliases, not hard-coded runtime lanes unless a deployment explicitly configures them.

## Plugin model

Adapters can be created to do anything, but they should declare:

```text
name
input contract
output contract
side effects
network access needs
filesystem access needs
endpoint compatibility
```

## Safety

Adapters that touch shell, network, filesystem, credentials, browser automation, or external APIs should declare their capability boundaries and approval model.
