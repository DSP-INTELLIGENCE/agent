# Docs Consistency Audit Plan

Milestone:

```text
agent-repo-docs-consistency-audit-v1
```

Contract to audit against:

```text
/prompt = direct LLM
/ground = grounded/RAG LLM
/summon = persona/session control and /summon prompt
codec prompt = /prompt
codec ground = /ground
/question = legacy/unwired
/rag and /research = not lanes
semantic router, AgentSpec, AgentScript, encoder routing = not runtime authority
```

Search command:

```bash
grep -RIn '/question\|/rag\|/research\|semantic router\|AgentSpec\|AgentScript\|encoder' \
  README.md AGENTS.md HANDOFF.md PATCH.md CODEC.md GROUND.OUTLINE.md AI.OUTLINE.md PATCH.HANDOFF.md docs core tests codec.py codec-patch.py agent-cli.py \
  --exclude-dir=.git --exclude-dir=.venv --exclude='*.pyc'
```

Classify hits:

```text
OK: legacy/unwired warning
OK: test asserts legacy rejection
OK: historical context
BAD: active command mapping
BAD: user-facing help advertises removed lane
BAD: docs say /question is active
BAD: roadmap says semantic router executes
BAD: AgentSpec/AgentScript shown as runtime authority
```

Report sections:

1. Runtime consistency
2. Codec frontend consistency
3. Patcher workflow consistency
4. Docs consistency
5. Forbidden legacy surfaces found
6. Required fixes
7. Suggested next patch packages
