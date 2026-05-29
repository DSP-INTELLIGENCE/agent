# Project Memory

## Architecture

```text
/prompt = direct base LLM lane
/ground = grounded/RAG lane
/summon = persona/session control and explicit /summon prompt
```

Do not add or revive:

```text
/question
/rag
/research
legacy answer-like prompt templates
semantic router execution
AgentSpec execution
AgentScript execution
encoder routing as runtime authority
```

## Grounding

The adapter layer exists. The live bridge does not.

Not yet trusted:

```text
Live /ground -> EvidencePacket bridge
/grounding packet-first display
/sources packet-first display
```

## Patcher

Use `codec-patch.py` as operator.

Sequence:

```text
review -> inspect report -> publish -> merge-cleanup
```

Do not publish if the report misses untracked files.

## Incident lessons

Failure modes observed:

```text
package run on main
dirty worktree before apply
heredocs/pasted markdown into terminal
report missing untracked files
nested ZIP root instead of flat ZIP root
runtime bridge attempted too early
```

Permanent mitigations:

```text
flat ZIP root
temp branch only
review first
no heredocs
stop on dirty
report must include all expected paths
```
