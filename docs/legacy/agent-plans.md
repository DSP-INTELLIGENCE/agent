# Agent Plans And Ideas

This document captures active planning ideas for the agent core.

The purpose is to keep roadmap ideas visible without mixing them into runtime code before the architecture is ready.

## Core Boundary

The agent core should stay small and deterministic.

Core responsibilities:

- switch matrix
- front doors
- routing
- policy
- grounding
- patch orchestration
- manifest-gated execution

External CLI payloads should stay outside the core repo and bind back through manifests and domain frontends.

## Local Runtime Environment

The agent should own a local `.venv` inside the agent folder.

Goals:

- isolate agent dependencies
- support reproducible development
- support PyPI package search/build/install flows
- avoid polluting system Python
- provide a stable runtime for patcher, web, grounding, and CLI bindings

## Model And Provider Lanes

The agent can use local and external model backends through explicit front doors and policy checks.

Potential Ollama lanes:

- coding models: Qwen-Coder, gpt-oss, code-specialized models
- general models: llama3 and similar general-purpose models
- vision models: Gemma 3, Llama Vision, and related multimodal models

Model use should remain explicit:

- provider selection is not policy
- model selection is not tool execution
- LLMs synthesize, explain, and assist
- runtime and switch policy decide what is allowed

## Patch And Self-Editing Lane

The patch runner is the safest path for agent self-modification.

Future goals:

- integrate patcher into the agent front door
- allow the agent to request patches from Codex CLI
- allow the agent to talk to Codex to generate patch packages
- validate patches through checksums, metadata, policy classes, smoke tests, and replay reports
- support GitHub, `git`, `gh`, local git servers, and scaffolded git repo directories

Rule:

```text
agent may propose patches
patcher validates and applies patches
git records accepted changes
```

## Linux Domain Frontends

Domain frontends are routing namespaces, not bundled tool collections.

Planned domains:

- `/linux`: system tools, `/usr/bin`, `/bin`, `/usr/local/bin`, `PATH`, `LD_LIBRARY_PATH`
- `/apt`: apt package system
- `/audio`: ALSA, PulseAudio, JACK, and CLI audio tools
- `/image`: image tools, GIMP, photo editing CLI tools
- `/video`: video tools
- `/speech`: speech synthesis and recognition CLI tools
- `/network`: network tools, internet tools, nmap, ifconfig, networking CLIs
- `/python`: Python, code generation, linting, checking, PyPI, virtualenvs
- `/c`: C language tools, gcc, compilers
- `/cpp`: C++ tools, g++, GNU tools, other compilers
- `/search`: web search, file system search, scrapers, httrack-style tools
- `/system`: system tools
- `/ubuntu`: Ubuntu-specific tools
- `/gnome`: GNOME desktop/system tools

## AI And Research Domains
