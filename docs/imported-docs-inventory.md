# Imported Docs Inventory

The uploaded documentation bundle contained root docs, active design docs, roadmaps, audits, handoffs, tool notes, and prompt templates.

## Condensed into active docs

| Old area | Clean destination |
| --- | --- |
| `AGENT.md` | `AGENT.md`, `docs/architecture.md`, `docs/runtime-boundaries.md` |
| `TOOLS.md` | `TOOLS.md`, `docs/tool-bridge.md` |
| switch matrix docs | `docs/switch-control-plane.md`, `docs/runtime-boundaries.md` |
| CLI usage docs | `docs/cli-usage.md` |
| LLM provider/model docs | `docs/llm-control-plane.md` |
| session cache README | `docs/session-cache.md` |
| knowledge index README | `docs/knowledge-index.md` |
| roadmap variants | `docs/roadmap.md` |

## Historical material not restored as active docs

The bundle also contained dated branch audits, Codex handoffs, prompt templates, and multiple overlapping roadmap variants. Those are useful history, but they should not be restored directly into the active docs tree without an archive prefix.

Recommended archive location if needed later:

```text
docs/archive/YYYY-MM-DD/<original-file-name>.md
```

## Cleanup rule

Do not keep multiple files claiming to be the current roadmap or master outline. Keep one active roadmap and link to archived history from there.
