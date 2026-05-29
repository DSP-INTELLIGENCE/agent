# Codec Handoff Prompt

Work in the codec repo only.

```bash
cd ~/Downloads/codec
source .venv/bin/activate 2>/dev/null || true
```

Remote: https://github.com/DSP-INTELLIGENCE/codec

Do not work in the Agent repo unless explicitly asked. Do not assume Agent layout applies.

## Current checkpoint

The codec repo was recovered to a working checkpoint after reverting a bad package-skeleton move. Verify instead of assuming.

Expected historical checkpoint:

```text
413b286 Revert "create codec package skeleton"
```

## Repo role model

```text
codec.py                         clean user/operator frontend
codec-patch.py                   patch/package operator
scripts/codec_patch_install.py   staged patch workflow engine
agent-cli.py                     compatibility/legacy CLI surface
```

## Required first action

Run the audit commands from READ.FIRST.BEFORE.ANYTHING.md and report results. Do not change files before that report.

## Patch workflow

```text
review -> inspect report -> publish -> merge-cleanup
```

Expanded:

```text
review:        branch -> inspect -> preflight -> apply -> test -> report
publish:       commit -> push
merge-cleanup: merge -> push -> cleanup
```
