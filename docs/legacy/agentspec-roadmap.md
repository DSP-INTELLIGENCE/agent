# AgentSpec Roadmap

AgentSpec turns intent into contracts, not actions.

executor = never in agentspec.

AgentSpec is intentionally narrow:

- decode, validate, route, dispatch, and render are non-executing contract helpers
- external runtimes consume rendered artifacts later
- no shell execution
- no tool calls
- no model calls
- no mutation
- no orchestration

Current contract scope:

- schema export
- policy validation
- deterministic decode
- deterministic route selection
- deterministic dispatch preview
- deterministic renders for codex, verify-sh, and checklist
- exact route/dispatch consistency across helpers and CLI

Future-only:

- optional LLM decoder
- execution contract types
- review contract types
- planning contract types
- memory contract types
