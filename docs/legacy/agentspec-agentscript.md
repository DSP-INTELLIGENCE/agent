# AgentSpec and AgentScript

AgentSpec and AgentScript are separate layers.

## Core split

```text
AgentSpec = contract layer
AgentScript = executable script format
compiler = AgentSpec -> AgentScript
runner = execution authority
frontend = interaction layer
```

## AgentSpec

AgentSpec describes work. It does not execute.

AgentSpec owns contracts such as:

```text
TaskSpec
PolicySpec
ValidationSpec
DeliverySpec
RouteDecision
DispatchDecision
```

AgentSpec may decode, validate, route, dispatch dry-run, render, and export schema. It must not run shell commands, invoke patch runner, call tools, call models, mutate files, or start background workers.

## AgentScript

AgentScript is explicit script text for future runner execution.

AgentScript v1 should be parse/render first:

```text
# agent-script v1
# title: Inspect README
# mode: inspect
# route: inspect

/read README.md
/tree docs
``` 

Initial features:

```text
comment metadata header
comments
blank lines
slash commands
fenced paste blocks
deterministic to_dict()
stable render round trip
```

Initial non-goals:

```text
runner
execution
subprocess
mutation
compiler integration
registry validation
loops
conditionals
variables
background jobs
hidden retries
```

## Compiler

The compiler emits AgentScript. It never runs scripts.

Recommended target order:

```text
inspect
docs_only
validation
repo_patch
```

Start with inspect because it is read-only and safest.

## Runner

The runner is the only execution authority.

Runner should execute only validated, registered, approved AgentScript commands. Early runner migration should start with read-only repo-local lanes such as:

```text
/read
/tree
/find
/search repo
```

Later lanes:

```text
/ground
/web
/scrape
/patch
/python
/shell
/codex
```

## Approval

Approval grants belong to runtime policy and audit logs, not compiled script authority. AgentScript may request authority, but it should not embed `approved=true` as a source of authority.
