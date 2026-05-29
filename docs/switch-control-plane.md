# Switch Control Plane

`/switch` is the capability control plane.

It answers questions like:

```text
is this capability visible?
is it enabled?
is it plannable?
is it dispatchable?
which backend or provider is selected?
why is it blocked?
```

## What `/switch` is not

`/switch` is not a tool runner.

It should not:

- execute CLI tools
- call LLM providers
- edit files
- run shell commands
- bypass `/tool`
- invent fuzzy actions

## Desired route check

```text
requested route
  -> capability id
  -> switch state
  -> route validator
  -> allow, plan-only, read-only, or block
```

## Switch states

A useful route record should be able to express:

```text
visible: true | false
enabled: true | false
plannable: true | false
dispatchable: true | false
backend: optional selected backend
provider: optional selected provider
blockers: list of reasons
```

## Profiles

Switch profiles should be presets for capability state. They are useful for modes such as:

```text
safe local CLI only
read-only research
LLM enabled but tools disabled
image tools enabled
coding tools enabled
```

Applying a profile should update switch state. It should not execute the tools that the profile enables.

## Family preference

Tool-family preference is allowed as a narrow ranking hint:

```text
/switch story
/switch image
/switch code
```

That preference should only help choose among already-matching tools. It should not create broad fuzzy dispatch.
