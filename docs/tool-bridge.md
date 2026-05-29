# CLI Tool Bridge

`/tool` is the explicit execution bridge from `agent` to Linux CLI tools.

## Flow

```text
/tool <tool-id> [args]
  -> load manifest for <tool-id>
  -> validate flags and positionals
  -> validate command path
  -> execute with shell=False
  -> bound stdout/stderr
  -> return terminal output
```

## Manifest responsibilities

A CLI manifest should describe:

```text
id
name
description
command path
allowed flags
allowed positionals
timeout
output expectations
capability metadata
```

## Bridge responsibilities

The bridge should enforce:

- no unknown tool id
- no unknown flags
- no malformed positional arguments when schema exists
- no command path outside allowed locations
- no shell string execution
- timeout
- bounded stdout/stderr

## Tool help

Every tool should support one or more discoverability paths:

```text
/tool list
/tool show <tool-id>
/tool <tool-id> --help
```

## Large external tools

Large tools do not need to live inside this repo. Prefer a sibling tool repository or folder and keep only connector manifests in `agent`.

Example:

```text
../mega-tools/tools/<tool>/<entrypoint>.py
data_agent/plugins/cli/<tool-id>.json
```
