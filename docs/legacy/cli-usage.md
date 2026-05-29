# CLI Usage

Start the agent:

```bash
./agent.sh
```

or:

```bash
python3 agent.py
```

## Basic commands

```text
/help
/switch
/switch status
/tool list
/tool show <tool-id>
/tool <tool-id> --help
```

## Multiline paste

```text
/paste
multiple lines of input
/endpaste
```

`/paste` only collects text. The final collected block is submitted to the normal router.

## Explicit tool execution

```text
/tool project.grep --help
/tool manifest.lint --help
/tool session.cache stats
```

## Switch examples

```text
/switch status
/switch profile list
/switch profile apply <profile-name>
/switch story
/switch image
/switch code
```

Family switch commands should set preference only. They should not run a tool directly.

## Debug habit

When behavior is surprising, inspect in this order:

```text
1. /switch status
2. /tool show <tool-id>
3. manifest JSON under data_agent/plugins/cli/
4. route examples and aliases under data_agent/nlp/
5. core switch validator behavior
```
