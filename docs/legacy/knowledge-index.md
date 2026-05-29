# Knowledge Index

The knowledge index is a persistent local retrieval tool exposed through `/tool`.

## Purpose

Use it for local project notes, Markdown, text, JSON, CSV, and PDF text extraction when persistent retrieval is useful.

## Boundary

The index is a tool, not the router. It should be called explicitly or through a validated route.

## Local data

Generated databases should stay out of git.

Recommended pattern:

```text
data/mega.knowledge.sqlite
```

or another ignored local data path.

## Expected behavior

A knowledge tool may:

- index files
- chunk text
- search by FTS or metadata
- return context packets
- report extraction errors

It should not silently crawl unrelated paths or mutate source files.
