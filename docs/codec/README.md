# Codec Roadmap + Handoff Documentation Bundle

Generated: 2026-05-29T19:33:16Z

Documentation-only bundle for continuing work in the codec repo.

Repo: https://github.com/DSP-INTELLIGENCE/codec

Local start:

```bash
cd ~/Downloads/codec
source .venv/bin/activate 2>/dev/null || true
```

Highest-level decision: the codec repo is the source of truth. The Agent repo is out of scope unless explicitly reintroduced later.

Read order:

1. READ.FIRST.BEFORE.ANYTHING.md
2. HANDOFF.md
3. ROADMAP.md
4. CODEC_ARCHITECTURE.md
5. CODEC_PATCHER_USAGE.md
6. PATCH_PACKAGE_SPEC.md
7. CODEX_CLI_INTEGRATION.md
8. RECOVERY_AND_RESET.md

Golden rule:

```text
read repo -> temp branch -> flat ZIP -> review -> inspect report -> publish -> merge-cleanup
```
