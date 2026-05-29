# Handoff

Current priorities:

1. Audit docs for stale lane claims.
2. Fix codec frontend so `codec ground -> /ground`.
3. Fix patch report to include untracked/new files.
4. Integrate patch engine into `agent-cli.py install patch`.
5. Only then retry live `/ground` EvidencePacket bridge.

Safe patch workflow:

```text
review -> inspect report -> publish -> merge-cleanup
```

Known hazards:

```text
stale /question docs
patcher report missing untracked files
broken ground bridge must not be revived without v2 plan
```
