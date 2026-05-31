# Roadmap Normalization

## Purpose

Normalize the roadmap so it reflects the current repository architecture and does not mix legacy frontend ownership with the active codec workflow.

## Audit / Inspect

- Inspect roadmap files.
- Search for old frontend ownership language.
- Search for stale lane names.
- Search for legacy semantic execution language.
- Check active docs against `CODEC.md`, `INSTRUCTIONS.md`, and `docs/ARCHITECTURE.md`.

## Patch Plan

- Establish `codec.py` as the canonical operator/frontend surface.
- Establish `codec-patch.py` as the staged patch operator.
- Mark `agent-cli.py` as legacy CLI/backend compatibility.
- Mark `agent.py` as legacy terminal compatibility.
- Separate current architecture from historical and legacy notes.
- Update checked and unchecked milestone lists.
- Ensure roadmap language matches current docs.

## Verification

Run these commands:

    rg -n 'canonical terminal|backend boundary|operational boundary|/question|/switch|/tool' roadmap docs README.md INSTRUCTIONS.md
    python -m pytest
    git diff --stat

## Status

- [ ] Audit complete
- [ ] Roadmap updated
- [ ] Milestone added
- [ ] Tests passed
- [ ] Patch reviewed
- [ ] Committed
