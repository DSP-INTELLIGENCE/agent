# Agent

Agent is an AI-native terminal runtime organized around explicit lanes.

Core rule:

```text
No lane, no LLM.
```

LLM-facing contract:

```text
/prompt  direct base LLM lane
/ground  grounded/RAG answer lane
/summon  persona/session control; /summon prompt is explicit persona-routed prompting
```

Codec frontend:

```text
codec prompt -> /prompt
codec ground -> /ground
codec patch  -> patch/package workflow
```

Legacy/unwired command names are not aliases:

```text
/question /rag /research /write /generate /discuss /explain /describe /summarize /analyze /list /story
```

Support surfaces may exist, but are not additional answer lanes:

```text
/llm /codex /search /web /scrape /read /ls /tree /find /patch /tool /switch /grounding /sources
```
