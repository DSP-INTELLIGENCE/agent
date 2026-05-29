# Architecture

`agent` is a Linux CLI switchboard with a small deterministic core.

## System model

```text
terminal input
  -> input collection
  -> slash parser or natural-language router
  -> route signal
  -> switch spine
  -> route validation
  -> front door or /tool bridge
  -> terminal output
```

## Core components

```text
agent.py
  Thin process entrypoint.

core/main.py
  Starts the terminal runtime.

core/agent_runtime.py
  Coordinates interactive behavior and command dispatch.

core/switch_spine.py
  Resolves switch state for capabilities and routes.

core/switch_route_validator.py
  Blocks disabled, hidden, or unsafe routes before dispatch.

core/cli_bridge.py
  Executes manifest-gated CLI tools.

core/plugins.py
  Loads plugin/tool metadata.
```

## Data components

```text
data_agent/plugins/cli/*.json
  CLI tool manifests.

data_agent/switches/*.json
  Switch matrices, capability seeds, and profiles.

data_agent/nlp/*.json
  Route examples, aliases, exact aliases, and tool-family hints.
```

## Design rule

The core does not need to be intelligent. It needs to be predictable.

Intelligence can be layered on top through routing, LLM front doors, retrieval tools, and external CLI tools, but execution should still pass through explicit switch and manifest boundaries.

## Correct dependency direction

```text
runtime reads switch state
runtime asks validator for permission
runtime calls CLI bridge or front door
CLI bridge reads manifest
manifest points to tool code
tool code returns output
```

Avoid reversing this direction. Tools should not own the core router.
