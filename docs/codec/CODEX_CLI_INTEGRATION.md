# Codex CLI Integration Plan

## Purpose

Codex may be integrated into `codec-patch.py` as a repair/package-generation helper. It must not become an executor for commit, push, merge, or cleanup.

## Public reference notes

The OpenAI Codex CLI supports non-interactive/scripted use with `codex exec`, and Codex reads project instruction files such as `AGENTS.md`. Use those ideas, but keep execution under the staged workflow.

## Target command

```bash
python codec-patch.py repair <patch.zip> \
  --repo . \
  --with-codex \
  --codex-profile or-openai-gpt-oss-120b-free \
  --review-log logs/<review-log>.txt
```

## Codex may

```text
inspect failed package
inspect review log
read CODEX.md / CHATGPT.md from package
diagnose failure
create corrected v2 ZIP
write repair report
verify flat-root package shape
scan dangerous shell patterns
```

## Codex must not

```text
apply to main
commit
push
merge
delete branches
run sudo
install packages
run curl | sh
run wget | sh
hide failed tests
```

## Invocation

Use non-interactive Codex:

```bash
codex exec --profile or-openai-gpt-oss-120b-free "<repair prompt>"
```

Do not launch the Codex TUI from inside the patcher.

## Testing

Mock subprocess. No real Codex calls in tests.
