# Codec Frontend Plan

`codec.py` should be the clean user/operator frontend.

Target:

```text
codec.py        clean frontend
agent-cli.py    batch/legacy compatibility frontend
codec-patch.py  patch package operator
agent runtime   owns /prompt, /ground, sessions, tools, EvidencePacket
```

Answer commands:

```bash
python codec.py prompt "Hello"
python codec.py ground "What is pie?"
```

Mapping:

```text
codec prompt -> /prompt
codec ground -> /ground
```

Never:

```text
codec ground -> /question
```

Tool/control wrappers may include:

```text
patch llm codex search web scrape read ls tree find tool switch/status
```

These are not additional answer lanes.
