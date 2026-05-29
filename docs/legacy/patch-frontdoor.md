# Patch Front Door

`/patch` is the planned agent front door for applying patch packages through the existing patch runner.

The front door should not implement patch logic itself. It should call the repo-local runner through `./scripts/agent_python.sh` so all patch behavior remains centralized in `scripts/agent_patch_runner.py`.

## Purpose

- give the agent a safe self-editing lane
- keep patch validation centralized
- make dry-run the default posture
- expose replay/audit reports through the agent UI
- avoid direct file mutation by LLMs

## Command Contract

Initial command surface:

```text
/patch dry-run <patch.zip>
/patch apply <patch.zip>
/patch replay <reports/.../run.json>
/patch status
```

Aliases may be added later, but the explicit forms above should remain stable.

## Default Safety Rules

- `/patch dry-run` never mutates the repository.
- `/patch apply` may apply changes but should not commit or push by default.
- commit and push must require explicit future flags.
- `/patch replay` is non-mutating audit mode.
- `/patch` should reject missing paths clearly.
- `/patch` should preserve patch runner reports.

## Runner Mapping

Expected implementation mapping:

```bash
./scripts/agent_python.sh scripts/agent_patch_runner.py <patch.zip> --dry-run
./scripts/agent_python.sh scripts/agent_patch_runner.py <patch.zip>
./scripts/agent_python.sh scripts/agent_patch_runner.py --replay <run.json>
```

Future commit/push mapping should remain explicit:

```bash
./scripts/agent_python.sh scripts/agent_patch_runner.py <patch.zip> --commit "message"
./scripts/agent_python.sh scripts/agent_patch_runner.py <patch.zip> --commit "message" --push
```

## Response Contract

The agent should report:

- command attempted
- status
- report directory
- `summary.md` path
- `run.json` path when available
- whether repository mutation occurred

## Non-Goals

- do not duplicate patch validation logic in the agent front door
- do not let `/patch` bypass `agent_patch_runner.py`
- do not auto-push
- do not use `/patch` to execute arbitrary shell commands
- do not hide failed summaries

## Implementation Order

1. Document this command contract.
2. Add parser support for `/patch` commands.
3. Route commands to `./scripts/agent_python.sh scripts/agent_patch_runner.py`.
4. Return summary/report paths in the agent response.
5. Add tests for dry-run, apply failure, and replay.

## Principle

```text
agent proposes
patch front door routes
patch runner validates
git records
```

<!-- agent-codec-docs-tighten-v2-frontdoor:start -->
## Current operator status

The active patch operator is `codec-patch.py` using staged workflows:

```text
review -> inspect report -> publish -> merge-cleanup
```

Older `/patch dry-run`, `/patch apply`, and `/patch replay` descriptions in this
file are legacy/planned front-door notes unless they are explicitly wired to the
same staged patch engine and safety contract.

Current patch operations should not bypass `codec-patch.py` / the canonical patch
engine, should not manually apply `change.patch`, and should not publish before a
clean review report is inspected.
<!-- agent-codec-docs-tighten-v2-frontdoor:end -->
