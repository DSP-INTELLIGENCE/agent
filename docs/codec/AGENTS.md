# AGENTS.md for Codec Repo Work

## Scope

Work in codec only:

```bash
cd ~/Downloads/codec
```

Do not inspect or patch Agent unless explicitly instructed.

## Read first

Read `READ.FIRST.BEFORE.ANYTHING.md`, `README.md`, `PATCH.md`, `HANDOFF.md`, and `CODEC.md` if present. Then inspect `codec.py`, `codec-patch.py`, `scripts/codec_patch_install.py`, and `agent-cli.py`.

## Patch workflow

Use temp branches and `codec-patch.py`. Never edit directly on main. Never publish before review.

## Safety

Do not run sudo, package installs, curl | sh, wget | sh, rm -rf /, mkfs, dd to devices, or privileged Docker. Do not paste terminal transcripts back into Bash.
