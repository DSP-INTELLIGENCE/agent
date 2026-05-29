# ChatGPT Handoff Prompt

We are working on `~/Downloads/agent`, repo `DSP-INTELLIGENCE/agent`.

Do not implement first. Audit first.

Current contract:

```text
/prompt = direct base LLM lane
/ground = grounded/RAG answer lane
/summon = persona/session control and explicit /summon prompt
```

Known issue:

```text
codec ground was found mapping to /question.
A v1 patch fixed it but report missed the untracked test file.
Need v2 package, not v1 publish.
```

Hard rules:

```text
No direct edits on main.
No heredocs.
No manual change.patch.
No publish before review.
Stop on dirty worktree.
Stop on unexpected diff.
```

Next safe milestones:

```text
agent-repo-docs-consistency-audit-v1
agent-codec-ground-route-v2
agent-codec-patcher-report-v1
agent-cli-patch-integration-v1
```
