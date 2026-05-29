# Codec Architecture

## Repo roles

```text
codec.py                         clean user/operator frontend
codec-patch.py                   patch/package operator
scripts/codec_patch_install.py   staged patch workflow engine
agent-cli.py                     compatibility/legacy CLI surface
```

## Frontend direction

Target commands:

```bash
python codec.py status
python codec.py prompt "Hello"
python codec.py ground "What changed?"
python codec.py patch review patch.zip --yes --branch patch/name
```

## Lane model

```text
prompt = raw/direct LLM
ground = grounded/RAG/research LLM
patch  = patch/package operator
```

Patch is not an LLM lane. Everything else is a tool/control surface.

## Non-goals

- Do not rebuild Agent.
- Do not move the package skeleton back.
- Do not revive legacy semantic/router layers.
- Do not add new LLM answer lanes.
