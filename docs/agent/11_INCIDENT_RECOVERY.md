# Incident Recovery

If the workflow starts spiraling:

1. Stop implementation.
2. Do not paste logs into Bash.
3. Open a fresh terminal.
4. Run only read-only audit commands.
5. Do not reset/clean/push unless explicitly approved.

Read-only audit:

```bash
cd ~/Downloads/agent
git status -sb
git log --oneline --decorate -10
git diff --stat
git diff b3e5925..HEAD -- core/agent_runtime.py
test -e tests/test_grounding_evidence_packet_runtime_bridge.py && echo "BRIDGE TEST EXISTS" || echo "bridge test absent"
```

Emergency abandon uncommitted patch branch, only after checking status:

```bash
git restore .
git clean -fd
git switch main
git branch -D patch/<name>
```
