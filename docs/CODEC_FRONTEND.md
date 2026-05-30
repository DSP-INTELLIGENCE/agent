# Codec Frontend

## Role

`codec.py` is the clean frontend tool for Agent.

It should expose simple operator commands and hide legacy invocation clutter.

## Current responsibilities

```text
codec prompt -> /prompt
codec ground -> /ground
codec status -> frontend/runtime diagnostics
codec patch -> codec-patch.py workflows
```

## Patch operator

`codec-patch.py` is the staged patch operator.

Canonical workflow:

```text
review -> publish -> merge-cleanup
```

Review runs:

```text
branch -> inspect -> preflight -> apply -> test -> report
```

Publish runs:

```text
commit -> push
```

Merge-cleanup runs:

```text
merge -> push -> cleanup
```

## Legacy surfaces

`agent.py` is the legacy terminal.

`agent-cli.py` is the legacy CLI/batch compatibility surface.

New operator work should prefer `codec.py` and `codec-patch.py`.
