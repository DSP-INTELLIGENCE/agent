# Tool Architecture

Tools connect to `agent` through explicit CLI manifests.

## Doctrine

```text
tool code is external behavior
manifest is the contract
/tool is the execution boundary
/switch controls whether the route is allowed
```

The core should not hardcode individual tool behavior except for small built-in control commands.

## Manifest bridge

Active tool manifests live under:

```text
data_agent/plugins/cli/
```

Each manifest should define enough information for the bridge and router to understand:

- tool id
- command path
- allowed flags
- positional arguments
- timeout
- description
- route/capability metadata when available

## Execution boundary

The CLI bridge should:

- load exactly one selected manifest
- reject unknown flags and invalid positionals
- keep command execution on an allowlisted path
- call subprocess with `shell=False`
- enforce timeout and bounded output
- capture stdout/stderr for display and optional session cache use

## Tool families

Tool families are preference hints, not execution shortcuts.

Examples:

```text
story
comic
image
sd
audio
code
knowledge
session
```

A family preference can help rank matching tools, but it must not create broad fuzzy execution.

## Imported tools

Imported tools should remain connected by manifests. Agent-owned runtime tools can live in `external CLI payloads/`; larger standalone tool suites should live outside this repo and be referenced by manifest paths.

Preferred relationship:

```text
agent repo
  core runtime
  manifests
  switch data
  docs

external tool repo or sibling folder
  actual large tool implementations
```
