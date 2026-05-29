# Milestones

## agent-repo-docs-consistency-audit-v1

Audit only. No file changes.

Goals:

- Classify every `/question`, `/rag`, `/research`, semantic router, AgentSpec, AgentScript, and encoder-routing mention.
- Find docs that still advertise removed lanes as active.
- Produce a report.

## agent-codec-ground-route-v2

Small frontend patch.

Goals:

- `codec.py ground` routes to `/ground`, not `/question`.
- Help text says `/ground`.
- Add non-live frontend tests.
- Package report shows both `codec.py` and `tests/test_codec_frontend.py`.

## agent-codec-patcher-report-v1

Patch engine quality fix.

Goals:

- Report stage includes untracked files listed in `changed-files.txt`.
- Diff stat includes new files.
- Full diff includes new files.
- Tests cover package adding a new file.

## agent-cli-patch-integration-v1

CLI integration.

Goals:

- `python agent-cli.py install patch --help` works.
- It delegates to `core/patch_install.py`.
- No second patch engine.

## agent-docs-lane-consistency-v1

Docs patch.

Goals:

- README/AGENTS/HANDOFF/PATCH/CODEC/GROUND docs match active contract.
- `/question`, `/rag`, `/research` are legacy/unwired only.

## agent-ground-runtime-evidence-packet-v2

Runtime bridge. High care.

Preconditions:

- Docs audit complete.
- Codec ground route fixed.
- Patcher report fixed.

Goals:

- Live `/ground` stores EvidencePacket.
- Synthesis uses packet answer context.
- `/grounding` and `/sources` are packet-first.
- No raw prompt fallback.
