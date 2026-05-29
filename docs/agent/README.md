# Agent Roadmap / Docs / Handoff Bundle v1

This ZIP is documentation-only. It contains no patch, no apply script, and nothing to execute.

Current contract:

```text
/prompt = direct base LLM lane
/ground = grounded/RAG answer lane
/summon = persona/session control; /summon prompt is explicit persona-routed prompting
```

Codec frontend target:

```text
codec prompt -> /prompt
codec ground -> /ground
codec patch  -> codec-patch.py / canonical patch engine
```

Legacy/unwired:

```text
/question /rag /research
/write /generate /discuss /explain /describe /summarize /analyze /list /story
semantic router execution
AgentSpec execution
AgentScript execution
encoder routing as runtime authority
```

Recommended next milestones:

1. `agent-repo-docs-consistency-audit-v1`
2. `agent-codec-ground-route-v2`
3. `agent-codec-patcher-report-v1`
4. `agent-cli-patch-integration-v1`
5. `agent-ground-runtime-evidence-packet-v2`

Use this bundle as a planning/handoff source. Convert individual docs into real repo patches only after review.
