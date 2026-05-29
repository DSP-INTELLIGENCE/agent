# Tools / Linux / Shell / LLM Wiring Plan

The LLM must not execute tools directly.

Correct flow:

```text
user request
  -> explicit lane or tool command
  -> planner creates structured action proposal
  -> policy validates action
  -> dispatcher executes approved action
  -> result packet
  -> LLM summarizes result if lane permits
```

Shell default:

```text
deny by default
read-only allowlist only
project-local only
no sudo
no root
no broad chmod
no rm -rf outside approved temp paths
no curl|sh
no wget|sh
no package installs
no privileged docker
```

LLM may:

```text
explain what a command would do
summarize tool result
propose next safe command
draft a patch plan
```

LLM may not:

```text
execute shell
invent results
bypass policy
turn plain text into shell
chain destructive commands
auto-approve mutation
```
