# Session Cache

`session.cache` is a temporary local cache for the current work session.

It is separate from a persistent knowledge index.

```text
session cache      temporary project/session context
knowledge index    persistent local retrieval corpus
```

## Typical commands

```text
/tool session.cache init
/tool session.cache clear
/tool session.cache stats
/tool session.cache load-text --title "note" --text "..."
/tool session.cache load-file --path README.md
/tool session.cache load-last-tool --title "last output"
/tool session.cache search --query "routing"
/tool session.cache context --query "switch spine" --top 3
/tool session.cache list
```

## Rules

- Keep it temporary by default.
- Keep paths project-local.
- OCR, URL loading, and expensive extraction should be explicit.
- Captured tool output should be opt-in and inspectable.
