# Codex / CLI Integration Plan

Codex is a repo operator, not runtime authority.

Codex should:

```text
run requested stages
report exact output
stop on failures
avoid manual edits
avoid broad refactors
avoid pushing/merging unless stage explicitly does that
```

Agent CLI patch integration milestone:

```text
agent-cli-patch-integration-v1
```

Goal:

```text
python agent-cli.py install patch --stage inspect
python agent-cli.py install patch --workflow review --yes --branch patch/name
```

It should delegate to:

```text
core/patch_install.py
```

No second patch engine.

Expected CLI surfaces:

```text
codec-patch.py                 package operator
codec.py patch                 frontend wrapper
agent-cli.py install patch     batch/legacy compatibility wrapper
```
