# Agent Virtual Environment

The agent should own a local `.venv` inside the agent repository.

This keeps runtime dependencies isolated from system Python and gives patcher, web, grounding, and CLI bindings a stable execution environment.

## Bootstrap

Run:

```bash
./scripts/bootstrap_venv.sh
```

Default behavior:

- creates `.venv/` at the repository root
- upgrades `pip`
- installs `requirements.txt` if present

## Overrides

Use a different Python interpreter:

```bash
AGENT_PYTHON=python3.12 ./scripts/bootstrap_venv.sh
```

Use a different virtual environment path:

```bash
AGENT_VENV_DIR=/tmp/agent-venv ./scripts/bootstrap_venv.sh
```

## Policy

The repo-local `.venv` is runtime state.

Rules:

- do not commit `.venv/`
- do not store secrets in `.venv/`
- do not treat `.venv/` as memory
- do not mix system packages with agent runtime dependencies
- prefer repeatable installs from checked-in requirement files when available

## Current Purpose

The `.venv` supports:

- patch runner execution
- future `/python` domain work
- PyPI search, build, and install workflows
- local provider/client dependencies
- isolated development and testing

## Python Wrapper

Run Python through the repo-local virtual environment:

```bash
./scripts/agent_python.sh --version
./scripts/agent_python.sh scripts/agent_patch_runner.py --help
```

The wrapper fails clearly if `.venv` is missing and asks the user to run `./scripts/bootstrap_venv.sh` first.
