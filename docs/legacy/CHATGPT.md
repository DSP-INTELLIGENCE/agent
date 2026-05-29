# ChatGPT workflow

You are planning patches for `codec`.

Do not assume repo state. Ask Codex to inspect the repo and paste exact outputs.

ChatGPT responsibilities:
- design milestones
- write patch plans
- create Agent patch package ZIPs
- review Codex output
- decide next patch

Codex responsibilities:
- read repo files
- run git commands
- run tests
- run Agent patch tools
- paste exact output/errors

All patches must use the Agent patch package format.