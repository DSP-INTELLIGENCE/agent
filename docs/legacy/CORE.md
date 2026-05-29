Below is the **complete Agent core outline** as it should be understood now, with `codec` as the encoder/decoder layer and `agent` as the local-first control plane.

The public `agent` README defines Agent as a local-first `/switchable` switchboard matrix: a policy-gated control plane for routes, tools, LLM providers, memory, knowledge, web systems, and Linux CLI-backed operations. It also defines the dispatch stack as `user input → slash parser → deterministic router → route signals → switch matrix → policy validator → plan / read / dispatch / block`. ([GitHub][1])

# Agent core outline

## 0. Core identity

```text
agent = local-first control plane
codec = encoder / decoder research-answer runtime
```

Agent is not just a chatbot and not just tools. Agent is the switchboard and policy runtime.

```text
Agent:
  slash parser
  lane registry
  semantic route control plane
  switch matrix
  policy validator
  command registry
  tool manifest bridge
  AgentScript runner
  patch runner
  terminal / CLI frontends

Codec:
  encoder
    semantic router
    grounding
    wikipedia
    dictionary
    web search
    scrape
    files
    corpus
    lanes to fire
    research packet

  decoder
    final LLM response only
```

The older README also states the explicit-lane principle: instructions route through declared lanes, lane contracts, and runtime handlers; the LLM is only used through explicit lanes and after the lane has produced or assembled the context it is responsible for. ([GitHub][2])

---

# 1. Frontends

## 1.1 `agent.py`

Interactive terminal frontend.

Responsibilities:

```text
read terminal input
support multiline paste helper
parse slash commands
call runtime/router/control-plane surfaces
print responses
```

Non-responsibilities:

```text
no core policy ownership
no semantic-router ownership
no evidence assembly ownership
no arbitrary direct LLM fallback
```

## 1.2 `agent-cli.py`

Non-interactive CLI frontend.

Intended shape:

```bash
python agent-cli.py run --text "/question what is cheese?"
python agent-cli.py run --file prompt.md
python agent-cli.py batch commands.txt
```

Responsibilities:

```text
batch automation
CI-friendly invocation
scriptable command execution
same policy/routing constraints as agent.py
```

## 1.3 `agent.sh`

Launcher wrapper for interactive use.

---

# 2. Core command principle

## 2.1 No lane, no LLM

The current repo README explicitly states:

```text
No lane, no LLM.
```

Plain text is not supposed to be sent directly to the model; it must route through an explicit lane such as `/prompt`, `/question`, `/web`, `/scrape`, `/ground`, `/explain`, or `/summarize`. ([GitHub][2])

## 2.2 Everything inspectable

Agent core rule from the switchboard README:

```text
everything advertises state
everything can be inspected
everything can be enabled or disabled
everything can be planned before dispatch
everything routes through policy gates
```

([GitHub][1])

---

# 3. Lane system

## 3.1 Lane registry

Core files visible in `core/` include registry and loader modules:

```text
core/command_registry.py
core/command_registry_loader.py
core/command_registry_render.py
```

These are part of the command/lane metadata system. ([GitHub][3])

Lane metadata should include:

```text
name
slash command
description
enabled
executor
uses_llm
requires_grounding
requires_web
requires_scrape
may_use_grounding
may_use_web
may_use_scrape
output_contract
risk
capabilities
metadata
```

## 3.2 Primary lanes

Current conceptual lanes:

```text
/prompt
/question
/web
/scrape
/ground
```

The README defines `/prompt` as direct raw LLM prompt, `/question` as grounded answer lane, `/web` as web/search collection, `/scrape` as scrape/extraction, and `/ground` as grounding diagnostics/evidence lane. ([GitHub][2])

## 3.3 Prompt-variant lanes

Prompt variants:

```text
/write
/generate
/discuss
/explain
/describe
/summarize
/analyze
/list
/story
```

These are explicit LLM lanes, not hidden fallback paths. Their metadata declares what context capabilities they may use later. ([GitHub][2])

## 3.4 Capability validation

Core file:

```text
core/lane_capability_validator.py
```

The validator decides whether a selected lane may use requested capabilities. It should remain between semantic routing and runtime execution.

---

# 4. Semantic route control plane

## 4.1 Semantic router role

The README says semantic routing is **candidate generation only**:

```text
semantic router proposes
registry authorizes
runtime executes
```

It may suggest lanes, but it does not execute, authorize, call the LLM, call web/search/scrape/grounding, or bypass lane contracts. ([GitHub][2])

## 4.2 Core semantic-route modules

Current `core/` listing includes these semantic route modules:

```text
core/semantic_route_catalog.py
core/semantic_route_audit.py
core/semantic_route_diagnostics.py
core/semantic_route_dry_run.py
core/semantic_route_handoff.py
core/semantic_route_selection.py
core/semantic_route_threshold.py
core/semantic_router_adapter.py
core/semantic_routing.py
```

([GitHub][3])

## 4.3 Intended semantic route flow

```text
natural instruction
→ semantic route proposal
→ lane capability request
→ lane capability validator
→ route selection
→ threshold decision
→ diagnostics summary
→ handoff assessment
→ lane invocation
→ AgentScript / runtime later
```

## 4.4 Semantic route objects

Core control-plane objects:

```text
SemanticRouteProposal
LaneCapabilityRequest
SemanticRouteSelection
SemanticRouteThresholdDecision
SemanticRouteDiagnosticsSummary
SemanticRouteHandoffAssessment
LaneInvocation
SemanticRouteAuditArtifact
```

## 4.5 Threshold policy

Purpose:

```text
prevent overconfident route selection
detect low confidence
detect ambiguous candidates
ignore denied candidates in ambiguity checks
surface alternatives
```

Statuses:

```text
trusted
low_confidence
ambiguous
denied
empty
```

## 4.6 Handoff assessment

Purpose:

```text
combine diagnostics + threshold
decide whether route is safe for future invocation
```

Statuses:

```text
ready
not_ready
mismatch
empty
denied
low_confidence
ambiguous
```

---

# 5. Switch matrix

The switch matrix is the central control plane. The README lists planned switch surfaces:

```text
/switch
/switch list
/switch show
/switch on
/switch off
/switch mode
/switch reset
/switch profile
/switch plan
```

It also lists categories such as `core.router`, `core.llm`, `core.web`, `core.tools`, `core.shell`, `core.python`, `core.files`, `core.git`, and others. ([GitHub][1])

Core files:

```text
core/switch_spine.py
core/switch_route_validator.py
```

([GitHub][3])

## 5.1 Switch examples

```text
router.semantic.enabled
router.encoder.enabled
router.validator.strict
router.auto_dispatch.enabled

llm.enabled
llm.provider
llm.model
llm.streaming

web.enabled
web.live_enabled
web.extract.enabled

shell.enabled
shell.confirm_required

git.enabled
git.push_enabled
git.destructive_enabled
```

## 5.2 Switch rule

```text
routes do not decide alone
tools do not decide alone
LLM output does not decide alone
switch matrix + validator decides
```

([GitHub][1])

---

# 6. Runtime dispatch

Core files visible in `core/`:

```text
core/agent_runtime.py
core/execution_dispatch.py
core/execution_dispatch_render.py
core/events.py
core/main.py
```

([GitHub][3])

Runtime dispatch should do:

```text
receive validated command/lane invocation
check switch state
check policy
execute allowed runtime handler
produce structured output
record event/audit artifact
```

Runtime dispatch should not do:

```text
semantic guessing
hidden LLM fallback
unbounded shell execution
policy bypass
```

---

# 7. LLM front door

Core files:

```text
core/llm_config.py
core/llm_provider_config.py
core/llm_model_catalog.py
core/llm_model_selection.py
core/llm_open_webui_client.py
core/llm_chat_execution.py
core/llm_front_door.py
core/llm_frontdoor.py
core/llm_runtime_front_door.py
```

([GitHub][3])

## 7.1 LLM responsibilities

```text
manage provider config
select model
call Open WebUI / Ollama-compatible backend
apply prompt templates
execute only when lane permits LLM use
return structured result
```

## 7.2 LLM non-responsibilities

```text
not router authority
not evidence source
not policy validator
not hidden fallback for plain text
not executor of shell/web/git/files
```

The README explicitly lists “LLM as router” and “LLM as evidence source” among removed concepts. ([GitHub][2])

---

# 8. Grounding / search / web / scrape

Core directories visible under `core/`:

```text
core/ground/
core/search/
core/web/
core/scrape/
core/response_policy/
core/runtime_decoder/
```

([GitHub][3])

## 8.1 Ground

Purpose:

```text
source/evidence planning
grounding diagnostics
evidence reports
claim/source guardrails
```

Related file:

```text
core/grounding_source_guard.py
```

## 8.2 Search

Purpose:

```text
query planning
search collection
result normalization
source packet generation
```

## 8.3 Web

Purpose:

```text
web backend integration
current/live retrieval
page/result metadata
```

## 8.4 Scrape

Purpose:

```text
URL fetch
content extraction
readable text extraction
page packet output
```

## 8.5 Response policy

Purpose:

```text
decide what can be said from available evidence
block unsupported claims
prevent private/sensitive info leakage
force uncertainty when evidence is missing
```

---

# 9. AgentScript

Core files:

```text
core/agent_script.py
core/agent_script_validator.py
core/agent_script_capability_validator.py
core/agent_script_registry_validator.py
core/agent_script_validation_pipeline.py
core/agent_script_runner.py
```

([GitHub][3])

## 9.1 AgentScript role

AgentScript is executable script text, but only when passed to a runner. The README states that AgentSpec describes contracts, AgentScript represents executable script text, the compiler emits scripts, and the runner executes approved scripts. It also says registry, dispatch, render, policy, and semantic routing do not execute. ([GitHub][2])

## 9.2 AgentScript flow

```text
AgentSpec / LaneInvocation
→ compiler
→ AgentScript text
→ validation pipeline
→ runner dry-run
→ runner execution if explicitly enabled
→ report artifact
```

## 9.3 AgentScript features

```text
metadata comment header
comments
blank lines
slash commands
paste blocks
parse
render
to_dict
round trip
```

## 9.4 Runner responsibilities

```text
parse script
list executable steps
validate capabilities
validate registry
dry-run by default
execute only approved slash commands
produce report artifact
stop on error
```

---

# 10. LaneInvocation / compiler

Core files:

```text
core/lane_invocation.py
core/lane_invocation_compiler.py
```

([GitHub][3])

## 10.1 LaneInvocation role

```text
first typed contract for one trusted lane invocation after semantic route handoff readiness
```

Fields:

```text
schema_version
root
slash_root
raw_input
normalized_input
source
handoff_ready
selected_lane
selected_confidence
requested_capabilities
capability_decision
lane_metadata
output_contract
metadata
```

## 10.2 Compiler role

```text
LaneInvocation
→ AgentScript
```

Early targets:

```text
/read
/tree
/find
```

---

# 11. Command registry / manifest bridge

Core files:

```text
core/command_registry.py
core/command_registry_loader.py
core/command_registry_render.py
core/cli_bridge.py
core/plugins.py
```

([GitHub][3])

The README says `/tool` remains the explicit execution bridge. The manifest bridge validates tool IDs, allowed positionals, allowed args, boolean args, shell settings, timeout/output limits, and whether free args are allowed. ([GitHub][1])

## 11.1 Manifest bridge responsibilities

```text
load manifests
validate args
render help
enforce no shell unless declared
enforce timeout/output limits
execute only declared tools
```

## 11.2 Tool bridge surfaces

```text
/tool list
/tool list --verbose
/tool show <tool>
/tool help <tool>
/tool <tool> [args...]
```

---

# 12. Patch system

Scripts directory contains the Agent-owned patch package system. You specifically pointed this out, and the public repo confirms the scripts directory exists. ([GitHub][4])

Patch system components:

```text
scripts/make_patch_package.py
scripts/agent_patch_runner.py
```

## 12.1 Package shape

```text
change.patch
changed-files.txt
checksums.txt
package-manifest.json
patch.json
tests/smoke.sh
tests/verify.py
```

## 12.2 Patch runner responsibilities

```text
extract patch ZIP
verify manifest
verify checksums
enforce allowed paths
enforce forbidden paths
git apply --check
git apply
run package tests
run full tests
write report
rollback on failure
optionally commit
optionally push
```

## 12.3 Patch workflow

```bash
git status --short
git diff
python scripts/make_patch_package.py ...
python scripts/agent_patch_runner.py patch.zip --repo .
python scripts/agent_patch_runner.py patch.zip --repo . --commit "message"
git push
gh pr create
```

---

# 13. Linux CLI operation model

The README says Linux commands should not be treated as random shell strings. They should be classified operations:

```text
tool + action + target + options + permission + risk + persistence = operation
```

Operation phases:

```text
discover
read
plan
precheck
apply
verify
rollback
audit
```

The first safe policy is read-only catalog first, plan-only second, and apply-gated operations later. ([GitHub][1])

## 13.1 Shell rules

```text
no arbitrary shell by default
no hidden mutation
no sudo/apply/delete/write without switch approval
all shell-like operations classified
all risky operations require plan/precheck/verify/rollback
```

---

# 14. Planning surface

The README defines `/plan` as the explanation surface. It should explain route candidates, switch state, blocked-by rules, validator decision, whether dispatch would happen, and why dispatch is allowed or blocked. ([GitHub][1])

## `/plan` output shape

```text
input
route candidates
selected route
switch state
policy result
blocked_by
would_dispatch
reason
required confirmation
next safe command
```

---

# 15. Data/config layout

The README’s project layout includes:

```text
agent.py
agent.sh
agent_cli.py
core/
agent_tools/
data_agent/plugins/cli/
data_agent/plugins/cli_disabled/
data_agent/config/
data_agent/switches/
data_agent/nlp/
data_agent/prompt_templates/
data/
docs/
tests/
```

([GitHub][1])

## 15.1 `data_agent/`

Purpose:

```text
tool manifests
disabled manifests
switch profiles
operation catalogs
route examples
workflow specs
schemas/contracts
```

## 15.2 `docs/`

Purpose:

```text
durable roadmaps
prompt templates
architecture notes
design constraints
```

## 15.3 `tests/`

Purpose:

```text
unit tests
golden fixtures
dry-run tests
routing tests
runner tests
patch runner tests
semantic route tests
```

---

# 16. Codec boundary

`codec` should be separate from `agent`.

## 16.1 Agent owns

```text
switch matrix
lane registry
capability validator
command registry
tool manifests
AgentScript
patch runner
terminal / CLI frontend
policy gates
runtime dispatch
```

## 16.2 Codec owns

```text
encoder
decoder
research packet
semantic-router candidate scoring for research mode
ground/wiki/dictionary/web/scrape/files/corpus collection
lane firing for evidence production
final answer composition from packet
```

## 16.3 Correct codec flow

```text
input
→ encoder
    normalize
    semantic route candidates
    policy choose broad research lane
    collect ground
    collect wikipedia
    collect dictionary
    collect web_search
    collect scrape
    collect files
    collect corpus
    fire selected lane(s)
    assemble ResearchPacket
→ decoder
    final LLM response only
```

## 16.4 What codec must not become

```text
not terminal agent
not patch runner
not switch matrix
not arbitrary tool host
not shell executor without agent policy
not direct plain text fallback
```

---

# 17. Current core module map

From the public `core/` listing, current modules group roughly like this: ([GitHub][3])

```text
core/
  ground/
  response_policy/
  runtime_decoder/
  scrape/
  search/
  web/

  agent_runtime.py
  batch_runner.py
  cli_bridge.py
  codex_frontdoor.py

  command_registry.py
  command_registry_loader.py
  command_registry_render.py

  execution_dispatch.py
  execution_dispatch_render.py

  lane_capability_validator.py
  lane_invocation.py
  lane_invocation_compiler.py

  llm_chat_execution.py
  llm_config.py
  llm_front_door.py
  llm_frontdoor.py
  llm_model_catalog.py
  llm_model_selection.py
  llm_open_webui_client.py
  llm_provider_config.py
  llm_runtime_front_door.py

  semantic_route_audit.py
  semantic_route_catalog.py
  semantic_route_diagnostics.py
  semantic_route_dry_run.py
  semantic_route_handoff.py
  semantic_route_selection.py
  semantic_route_threshold.py
  semantic_router_adapter.py
  semantic_routing.py

  switch_route_validator.py
  switch_spine.py

  agent_script.py
  agent_script_runner.py
  agent_script_validator.py
  agent_script_capability_validator.py
  agent_script_registry_validator.py
  agent_script_validation_pipeline.py

  grounding_source_guard.py
  nlp_router.py
  patch_frontdoor.py
  plugins.py
  terminal_input.py
  events.py
  helpers.py
  defaults.py
  constants.py
  types.py
```

---

# 18. Clean dependency direction

```text
data/config
  ↓
registry / catalog
  ↓
router proposal
  ↓
capability validator
  ↓
threshold / diagnostics / handoff
  ↓
lane invocation
  ↓
AgentScript compiler / runtime dispatch
  ↓
executor / collector / LLM front door
  ↓
result / artifact / audit
```

For codec:

```text
lanes
  ↓
router
  ↓
encoder
  ↓
research packet
  ↓
decoder
```

Agent can call codec, but codec should not own Agent’s switch matrix unless imported through a thin adapter.

---

# 19. Hard rules to preserve

```text
No lane, no LLM.
Semantic router proposes only.
Registry authorizes.
Switch matrix gates.
Validator decides.
Runtime executes.
LLM composes only when lane allows it.
LLM is not evidence.
Plain text never bypasses lanes.
Shell is classified operation, not random command string.
Patch changes go through patch packages.
AgentScript does not execute until runner.
Compiler does not execute.
Policy/registry/render do not execute.
```

---

# 20. Recommended next repo split

## `agent`

```text
control plane
switch matrix
lane registry
capability validator
command registry
AgentScript
patch runner
CLI/terminal
safe local automation
```

## `codec`

```text
encoder
decoder
research packet
evidence collectors
semantic-router candidate scoring for research
answer synthesis from evidence
```

## Integration seam

```text
agent /question
→ call codec encoder
→ receive ResearchPacket
→ codec decoder or agent llm front door
→ result artifact
```

That keeps Agent as the policy-gated runtime and Codec as the answer/research engine.

[1]: https://raw.githubusercontent.com/DSP-INTELLIGENCE/agent/main/README.md "\" \
  \--body \"<summary and tests>\"
\```

\## Safety rules

Keep:

\```text
explicit tools
manifest-driven CLI bridge
switch-gated execution
small deterministic shortcuts
clear output contracts
patch-only changes by default
offline tests by default
\```

Avoid:

\```text
hidden route magic
special /paste behavior outside the terminal
broad automatic routing
unbounded shell execution
uncontrolled plugin args
unguarded Linux mutation
repo-spanning feature tangles
\```

\## Current roadmap

Near-term roadmap:

\```text
1\. agent_cli.py as CLI twin of agent.py
2\. switch.matrix read/plan tool
3\. /switch status/list/show/plan surface
4\. switch profiles
5\. /plan explains switch gating
6\. route validator consumes switch matrix
7\. /llm backed by switch matrix
8\. semantic encoder and spaCy become switchable signals
9\. gpt-web / webengine adapters
10\. gated apply/verify/rollback operations much later
\```

\## Documentation

Important docs:

\```text
AGENT.md
TOOLS.md
README_CODE_FEATURE_TOOL.md
docs/
docs/prompt_templates/
\```

Core architecture statement:

\```text
Agent is a /switchable switchboard matrix.

It classifies capabilities, advertises state, plans operations, validates risk,
and dispatches only when the switch matrix allows it.
\```
"
[2]: https://github.com/DSP-INTELLIGENCE/agent "GitHub - DSP-INTELLIGENCE/agent · GitHub"
[3]: https://github.com/DSP-INTELLIGENCE/agent/tree/main/core "agent/core at main · DSP-INTELLIGENCE/agent · GitHub"
[4]: https://github.com/DSP-INTELLIGENCE/agent/tree/main/scripts "agent/scripts at main · DSP-INTELLIGENCE/agent · GitHub"
