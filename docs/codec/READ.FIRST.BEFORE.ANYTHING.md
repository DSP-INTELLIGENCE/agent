# READ FIRST BEFORE ANYTHING

Stop and read the repo before doing any implementation.

## Required inspection

```bash
cd ~/Downloads/codec
source .venv/bin/activate 2>/dev/null || true

git status --short --untracked-files=all
git branch --show-current
git log --oneline --decorate -12

find . -maxdepth 3 \( \
  -name '*.md' \
  -o -name 'README*' \
  -o -name 'PATCH*' \
  -o -name 'HANDOFF*' \
  -o -name 'CODEC*' \
  -o -name 'READ.FIRST.BEFORE.ANYTHING.md' \
\) -print | sort
```

## Required reading

```bash
sed -n '1,260p' READ.FIRST.BEFORE.ANYTHING.md 2>/dev/null || true
sed -n '1,260p' README.md 2>/dev/null || true
sed -n '1,320p' PATCH.md 2>/dev/null || true
sed -n '1,320p' HANDOFF.md 2>/dev/null || true
sed -n '1,320p' CODEC.md 2>/dev/null || true

sed -n '1,280p' codec.py
sed -n '1,220p' codec-patch.py
sed -n '1,420p' scripts/codec_patch_install.py
sed -n '1,280p' agent-cli.py
```

## Required verification

```bash
python codec-patch.py --help
python codec.py --help
python agent-cli.py install patch --help
python -m py_compile agent-cli.py codec-patch.py codec.py scripts/codec_patch_install.py
python -m pytest -q
```

## Required audit output

Report branch, HEAD, clean/dirty state, docs read, architecture summary, patch workflow summary, patcher files, test result, and recommended next milestone.

## Absolute rules

- Work only in codec unless explicitly told otherwise.
- Read the repo first.
- Use a temp branch before changes.
- Do not edit directly on main.
- Do not publish until review is clean.
- Do not ignore untracked files.
- Do not manually apply change.patch.
- Do not paste terminal transcripts back into Bash.
- Do not use sudo, package installs, curl | sh, wget | sh, destructive filesystem commands, or privileged Docker.
