# AI Assistant Instructions for Patch Packages

Every staged patch package may include `CODEX.md` and `CHATGPT.md`. These are package-local instructions for AI helpers. They do not authorize execution.

## Codex role

Codex may inspect, diagnose, repair package metadata/scripts/tests, create a corrected v2 ZIP, verify flat-root ZIP shape, scan for dangerous patterns, and report exact commands/outputs.

Codex must not edit main directly, manually apply change.patch, commit, push, merge, delete branches, run sudo, install packages, run curl | sh, run wget | sh, run destructive filesystem commands, or ignore failed tests.

## ChatGPT role

ChatGPT may design patch scope, write instructions, review reports, explain failures, recommend recovery commands, and generate corrected package plans.

ChatGPT must not claim a package is safe without inspecting shape, recommend publish before clean review, ignore untracked files, mix unrelated fixes, or turn failed review into manual main-branch edits.
