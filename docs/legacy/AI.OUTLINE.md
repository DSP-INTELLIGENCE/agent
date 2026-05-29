# `/ai` adapter outline

## 1. Goal

`/ai` should not be a magical open-ended agent loop.

It should be a stable runtime path that turns a user request into a typed packet, runs enabled AI/reasoning providers, validates decisions, and optionally executes only approved actions.

```txt id="n8fc5i"
/ai <task>
  -> normalize task
  -> classify route
  -> extract structured facts
  -> call enabled AI providers
  -> collect AIProviderResult objects
  -> merge into AIPacket
  -> validate decisions and proposed actions
  -> optionally execute approved actions
  -> store packet for /aiing, /trace, /actions, /rules
```

The LLM should be only one provider in the system, not the whole system.

---

## 2. Boundary with existing commands

Keep command roles clean:

```txt id="so6k78"
/prompt
  direct LLM

/ground
  grounded answer through EvidencePacket

/ai
  reasoning, routing, planning, policy, tool/action decisioning

/summon
  persona/session control
```

`/ai` may call `/ground` internally as a provider or sub-step when it needs evidence, but `/ground` should not become the agent executor.

---

## 3. Core concept

For `/ground`, the stable object is:

```txt id="eqg8ss"
EvidencePacket
```

For `/ai`, the stable object should be:

```txt id="p7e711"
AIPacket
```

`AIPacket` is the full reasoning/control payload.

It should include:

```txt id="hxpxax"
input
normalized task
route
facts
predictions
rules fired
constraints
decisions
proposed actions
approved actions
blocked actions
tool results
diagnostics
status
```

Final rule:

```txt id="phhji9"
No tool executes unless it appears in AIPacket.approved_actions.
```

---

## 4. Core objects

### `AIFact`

A normalized fact about the task.

```python id="u89g87"
class AIFact(BaseModel):
    name: str
    value: Any
    source: str = "unknown"
    confidence_score: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Examples:

```txt id="i5jt3i"
needs_current_info = true
modifies_files = false
route = repo.patch
has_constraints = true
risk = high
user_confirmed = false
```

---

### `AIPrediction`

A learned or heuristic prediction.

```python id="ehngiz"
class AIPrediction(BaseModel):
    name: str
    value: Any
    provider: str
    confidence_score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Examples:

```txt id="fy9mwm"
task_type = research.software
risk = medium
needs_clarification = false
likely_tool = web_search
failure_probability = 0.18
```

---

### `AIRuleFire`

One symbolic rule activation.

```python id="cn6nqw"
class AIRuleFire(BaseModel):
    rule_id: str
    rule_name: str
    provider: str = "clipspy"
    facts_used: list[str] = Field(default_factory=list)
    produced: list[str] = Field(default_factory=list)
    explanation: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Examples:

```txt id="4m4o0c"
use_web_for_current_software_info
require_confirmation_for_side_effects
use_solver_for_constraints
block_shell_when_untrusted
```

---

### `AIConstraint`

A formal or semi-formal constraint.

```python id="tz6j38"
class AIConstraint(BaseModel):
    id: str
    kind: str
    expression: str
    source: str = "unknown"
    hard: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Examples:

```txt id="a9pn46"
must_not_modify_files_without_confirmation
must_use_web_for_current_info
must_not_execute_shell_without_approval
task_deadline_before_due_date
```

---

### `AIDecision`

A normalized decision made by the AI pipeline.

```python id="dpup75"
class AIDecision(BaseModel):
    id: str
    action: str
    allowed: bool
    requires_confirmation: bool = False
    reason: str | None = None
    source: str = "unknown"
    confidence_score: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Examples:

```txt id="kql630"
use_web_research
use_solver
ask_clarifying_question
require_confirmation
block_action
execute_read_only_tools
```

---

### `AIAction`

A proposed, approved, blocked, or executed action.

```python id="jlg7qp"
class AIAction(BaseModel):
    id: str
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    status: Literal[
        "proposed",
        "approved",
        "blocked",
        "executed",
        "failed",
        "skipped"
    ] = "proposed"

    risk: Literal["low", "medium", "high"] = "low"
    requires_confirmation: bool = False
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Examples:

```txt id="cjv3dl"
git_status
read_file
web_search
run_tests
write_patch
apply_patch
git_commit
git_push
send_email
```

---

### `AIToolResult`

Result of an executed tool.

```python id="x4s1ty"
class AIToolResult(BaseModel):
    action_id: str
    tool: str
    ok: bool
    stdout: str | None = None
    stderr: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

---

### `AIPacket`

The stable `/ai` payload.

```python id="m2dzps"
class AIPacket(BaseModel):
    schema_version: str = "1.0"

    input: str
    normalized_task: str
    profile: str = "general_ai"

    route: str | None = None
    route_confidence: float | None = None
    candidate_routes: list[dict[str, Any]] = Field(default_factory=list)

    facts: list[AIFact] = Field(default_factory=list)
    predictions: list[AIPrediction] = Field(default_factory=list)
    rules_fired: list[AIRuleFire] = Field(default_factory=list)
    constraints: list[AIConstraint] = Field(default_factory=list)

    decisions: list[AIDecision] = Field(default_factory=list)
    proposed_actions: list[AIAction] = Field(default_factory=list)
    approved_actions: list[AIAction] = Field(default_factory=list)
    blocked_actions: list[AIAction] = Field(default_factory=list)
    tool_results: list[AIToolResult] = Field(default_factory=list)

    diagnostics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    ok: bool = False
    status: str = "pending"
```

Suggested statuses:

```txt id="e8d8cj"
ok
partial
needs_confirmation
needs_clarification
blocked
no_route
provider_error
validation_failed
execution_failed
```

---

## 5. Provider interface

Every AI provider implements the same shape.

```python id="u3cet0"
class AIProvider(Protocol):
    name: str
    available: bool

    def run(
        self,
        packet: AIPacket,
        *,
        profile: str = "general_ai",
    ) -> AIProviderResult:
        ...
```

Providers receive the current packet and return additions.

They should not mutate global state directly.

---

### `AIProviderResult`

Normalized provider output.

```python id="b5zw1i"
class AIProviderResult(BaseModel):
    provider: str
    ok: bool

    facts: list[AIFact] = Field(default_factory=list)
    predictions: list[AIPrediction] = Field(default_factory=list)
    rules_fired: list[AIRuleFire] = Field(default_factory=list)
    constraints: list[AIConstraint] = Field(default_factory=list)
    decisions: list[AIDecision] = Field(default_factory=list)

    proposed_actions: list[AIAction] = Field(default_factory=list)
    approved_actions: list[AIAction] = Field(default_factory=list)
    blocked_actions: list[AIAction] = Field(default_factory=list)
    tool_results: list[AIToolResult] = Field(default_factory=list)

    diagnostics: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
```

Important rule:

```txt id="qwsybb"
Providers may propose.
Policy providers may approve or block.
Execution providers may execute only approved actions.
```

---

## 6. Provider types

### `SemanticRouteProvider`

Purpose:

```txt id="ne4k2d"
Use Semantic Router to classify task intent and candidate workflows.
```

Input:

```txt id="xpph4r"
normalized_task
```

Output:

```txt id="bvc5jt"
route
route_confidence
candidate_routes
facts:
  route = research.software
```

Good routes:

```txt id="zz219l"
research.software
repo.inspect
repo.patch
shell.command
solver.constraints
grounded.question
rewrite.text
file.analysis
rule.authoring
general.chat
```

---

### `LLMFactExtractorProvider`

Purpose:

```txt id="mcxoyw"
Use an LLM to extract typed facts, entities, constraints, and possible actions.
```

Should return structured output only.

Examples:

```txt id="bh8pw7"
needs_current_info = true
modifies_files = false
has_constraints = true
topic = software
target_language = python
```

Rules:

```txt id="jkk8d4"
LLM may extract facts.
LLM may suggest actions.
LLM may not approve risky actions.
LLM may not execute tools.
```

---

### `SklearnPredictionProvider`

Purpose:

```txt id="mx8tbg"
Use trained scikit-learn models for learned heuristics.
```

Predictions:

```txt id="kfdxjz"
task_type
risk
needs_clarification
likely_tool
expected_success
failure_probability
```

Models:

```txt id="nkfdl5"
TfidfVectorizer + LogisticRegression
LinearSVC
DecisionTreeClassifier
RandomForestClassifier
NearestNeighbors
```

Good first models:

```txt id="slpgoz"
risk_classifier
task_type_classifier
clarification_needed_classifier
tool_success_predictor
```

---

### `CLIPSpyRuleProvider`

Purpose:

```txt id="shvhq4"
Use CLIPS rules for deterministic symbolic reasoning and policy.
```

Input:

```txt id="c7rkpb"
facts
predictions
proposed actions
tool metadata
user confirmation status
```

Output:

```txt id="bwavkz"
rules_fired
decisions
approved_actions
blocked_actions
new derived facts
```

Good rules:

```txt id="jdcc79"
use_web_for_current_info
use_solver_for_constraints
require_confirmation_for_side_effects
block_destructive_shell
ask_clarification_when_low_confidence
inspect_git_status_before_repo_changes
block_execution_without_approved_action
```

---

### `GroundingProviderBridge`

Purpose:

```txt id="fsbmb5"
Allow /ai to request grounded evidence from /ground when needed.
```

Example:

```txt id="03i0d7"
If task needs current factual information:
  call GroundingService
  attach EvidencePacket reference or summary to AIPacket
```

This should reuse `/ground`, not duplicate it.

Output:

```txt id="yy0h6i"
facts:
  has_evidence_packet = true
metadata:
  evidence_packet_id = ...
```

Important:

```txt id="61xina"
/ai may use /ground as a provider.
/ground should not depend on /ai.
```

---

### `SolverProvider`

Purpose:

```txt id="jbnkit"
Use formal solvers for actual constraint reasoning.
```

Backends:

```txt id="6q3fbp"
Z3
OR-Tools
Clingo
CPMpy
```

Good for:

```txt id="fbkb1n"
scheduling
assignment
dependency constraints
configuration validity
plan feasibility
resource allocation
```

Output:

```txt id="9v18re"
solution
infeasible_reason
constraints_satisfied
decisions
```

---

### `ToolPlannerProvider`

Purpose:

```txt id="bc4p4m"
Convert decisions into proposed actions.
```

Example:

```txt id="b7pj0d"
decision = use_web_research
  -> propose action web_search

decision = inspect_repo
  -> propose actions git_status, list_files, read_readme

decision = run_tests
  -> propose action shell_command pytest
```

This provider proposes actions only.

---

### `SafetyPolicyProvider`

Purpose:

```txt id="lb7020"
Approve or block proposed actions.
```

Can be implemented using:

```txt id="cxpy4c"
CLIPSpy
Python policy checks
allowlists / denylists
tool metadata
user confirmation state
```

Output:

```txt id="ylbjyz"
approved_actions
blocked_actions
decisions
diagnostics
```

Rules:

```txt id="m72jrg"
read-only actions can be approved automatically
file writes require confirmation or patch preview
shell commands require sandbox and risk checks
git push requires explicit confirmation
network access requires declared purpose
```

---

### `ExecutionProvider`

Purpose:

```txt id="qer3ck"
Execute only approved actions.
```

Rules:

```txt id="zh3a2g"
Never execute proposed actions.
Never execute blocked actions.
Only execute AIPacket.approved_actions.
Capture stdout, stderr, exit code, errors.
Store tool results in packet.
```

Execution modes:

```txt id="g8b2qa"
dry_run
read_only
approval_required
execute
```

Default mode should be:

```txt id="aks72w"
dry_run or read_only
```

---

### `ReflectionProvider`

Purpose:

```txt id="nw5c0g"
Summarize what happened and classify outcome.
```

Output:

```txt id="xiblpl"
final_summary
outcome
failure_reason
suggested_next_step
training_example_candidate
```

This can use an LLM, but only after tool results are collected.

---

## 7. Provider registry

There should be one place that builds the AI service.

```python id="aq5vi9"
def build_default_ai_service(config: AIConfig) -> AIService:
    providers: list[AIProvider] = [
        SemanticRouteProvider.optional(config),
        LLMFactExtractorProvider.optional(config),
        SklearnPredictionProvider.optional(config),
        CLIPSpyRuleProvider.optional(config),
        GroundingProviderBridge.optional(config),
        SolverProvider.optional(config),
        ToolPlannerProvider.optional(config),
        SafetyPolicyProvider.optional(config),
        ExecutionProvider.optional(config),
        ReflectionProvider.optional(config),
    ]

    enabled = [p for p in providers if p.available]
    return AIService(enabled)
```

Provider availability should be graceful:

```txt id="rkbz4f"
dependency installed      -> provider enabled
dependency missing        -> provider skipped
model unavailable         -> diagnostic, not crash
API key missing           -> provider unavailable
solver missing            -> skip solver
policy failure            -> block, do not fallback silently
```

---

## 8. `AIService`

The service coordinates providers and builds an `AIPacket`.

```python id="yydrmt"
class AIService:
    def __init__(self, providers: list[AIProvider]):
        self.providers = providers

    def run(
        self,
        task: str,
        *,
        profile: str = "general_ai",
        mode: Literal["decide", "dry_run", "execute"] = "decide",
    ) -> AIPacket:
        packet = AIPacket(
            input=task,
            normalized_task=normalize_task(task),
            profile=profile,
            status="pending",
        )

        for provider in self.providers:
            if not should_run_provider(provider, packet, mode=mode):
                continue

            try:
                result = provider.run(packet, profile=profile)
            except Exception as exc:
                result = AIProviderResult(
                    provider=provider.name,
                    ok=False,
                    error=str(exc),
                    diagnostics={"exception_type": type(exc).__name__},
                )

            packet = merge_ai_provider_result(packet, result)
            packet = validate_ai_packet(packet)

            if packet.status in {"blocked", "needs_confirmation", "needs_clarification"}:
                break

        return finalize_ai_packet(packet)
```

Important:

```txt id="u3m44r"
Provider order matters.
ExecutionProvider should run last.
SafetyPolicyProvider must run before ExecutionProvider.
```

---

## 9. Suggested provider order

```txt id="zc44e7"
1. SemanticRouteProvider
2. LLMFactExtractorProvider
3. SklearnPredictionProvider
4. CLIPSpyRuleProvider
5. GroundingProviderBridge
6. SolverProvider
7. ToolPlannerProvider
8. SafetyPolicyProvider
9. ExecutionProvider
10. ReflectionProvider
```

For `mode="decide"`:

```txt id="tut253"
Skip ExecutionProvider.
```

For `mode="dry_run"`:

```txt id="1qfcrt"
Generate proposed/approved/blocked actions, but do not execute.
```

For `mode="execute"`:

```txt id="cv885a"
Execute only approved actions.
```

---

## 10. `/ai` runtime flow

Example:

```txt id="sw4bgk"
user: /ai research PyPI and GitHub for modern rule engines
```

Flow:

```txt id="uf8juo"
1. Router sends to ai.run
2. AIService normalizes task
3. Semantic Router identifies:
   route = research.software
4. LLM extracts facts:
   needs_current_info = true
   topic = software
   modifies_files = false
5. scikit-learn predicts:
   risk = low
6. CLIPSpy fires:
   use_web_for_current_software_info
7. GroundingProviderBridge calls /ground or GroundingService
8. ToolPlanner proposes:
   web_search
   github_search
   pypi_lookup
9. SafetyPolicy approves read-only research actions
10. ExecutionProvider runs only if mode=execute
11. AIPacket is stored
```

---

## 11. Packet-first introspection commands

Mirror `/grounding` and `/sources`.

```txt id="ms88zw"
/aiing
  show last AIPacket diagnostics

/actions
  show proposed, approved, blocked, executed actions

/rules
  show rules fired

/trace
  show provider-by-provider trace

/facts
  show extracted and derived facts

/decide <task>
  run /ai in decide mode, no execution

/dryrun <task>
  run /ai in dry_run mode, no execution
```

---

## 12. LLM usage rules

The LLM should be contained.

Allowed:

```txt id="yfg1f2"
extract facts
normalize messy user input
summarize tool results
explain decisions
draft possible plans
draft possible CLIPS rules for review
```

Not allowed:

```txt id="znct5z"
approve risky actions
execute tools
silently override rules
invent facts as confirmed
bypass packet validation
bypass SafetyPolicyProvider
```

Prompt rule:

```txt id="mv42km"
Return structured facts only.
Mark uncertainty explicitly.
Do not approve or execute actions.
Do not invent tool results.
```

---

## 13. CLIPSpy integration

CLIPS facts can be generated from `AIPacket`.

Example CLIPS templates:

```clips id="w41lwb"
(deftemplate task
  (slot route)
  (slot route-confidence)
  (slot needs-current-info)
  (slot topic)
  (slot modifies-files)
  (slot runs-shell)
  (slot sends-email)
  (slot changes-calendar)
  (slot has-constraints)
  (slot user-confirmed)
  (slot risk))

(deftemplate action
  (slot id)
  (slot tool)
  (slot risk)
  (slot modifies-files)
  (slot runs-shell)
  (slot requires-confirmation))

(deftemplate decision
  (slot action)
  (slot allowed)
  (slot requires-confirmation)
  (slot reason))
```

Example rules:

```clips id="c58w3w"
(defrule use-web-for-current-info
  (task
    (needs-current-info TRUE)
    (topic software))
  =>
  (assert
    (decision
      (action use-web-research)
      (allowed TRUE)
      (requires-confirmation FALSE)
      (reason "Current software information should be verified."))))
```

```clips id="htt5ny"
(defrule require-confirmation-for-file-modification
  (task
    (modifies-files TRUE)
    (user-confirmed FALSE))
  =>
  (assert
    (decision
      (action require-confirmation)
      (allowed FALSE)
      (requires-confirmation TRUE)
      (reason "File modification requires explicit confirmation."))))
```

```clips id="4gud7d"
(defrule block-unapproved-shell
  (action
    (tool shell)
    (runs-shell TRUE)
    (requires-confirmation TRUE))
  (task
    (user-confirmed FALSE))
  =>
  (assert
    (decision
      (action block-shell)
      (allowed FALSE)
      (requires-confirmation TRUE)
      (reason "Shell execution requires approval."))))
```

---

## 14. scikit-learn integration

The scikit-learn provider should be local and optional.

Training data comes from logs:

```json id="h5pqd0"
{
  "input": "delete old build files and push this repo",
  "route": "repo.maintenance",
  "facts": {
    "modifies_files": true,
    "uses_git_push": true
  },
  "risk": "high",
  "needed_confirmation": true,
  "outcome": "blocked_until_confirmation"
}
```

Possible models:

```txt id="eh846a"
task_type_classifier.pkl
risk_classifier.pkl
clarification_classifier.pkl
tool_success_model.pkl
```

Provider output:

```txt id="qjycbo"
AIPrediction(name="risk", value="high", provider="sklearn")
AIPrediction(name="needs_clarification", value=false, provider="sklearn")
AIPrediction(name="likely_tool", value="git", provider="sklearn")
```

---

## 15. Semantic Router integration

Semantic Router should classify routes, not approve actions.

Example route config:

```yaml id="db3pwr"
routes:
  - name: research.software
    utterances:
      - research pypi packages
      - find github repos
      - compare python libraries
      - latest ai tools

  - name: repo.patch
    utterances:
      - fix this repo
      - create a patch
      - inspect the codebase
      - run tests

  - name: shell.command
    utterances:
      - run this command
      - install dependencies
      - check terminal output

  - name: solver.constraints
    utterances:
      - solve this scheduling problem
      - find a valid assignment
      - satisfy these constraints
```

Output becomes facts:

```txt id="i1sutq"
route = research.software
route_confidence = 0.89
```

---

## 16. Tool safety

Every tool should have metadata.

```python id="m2w8eo"
class ToolSpec(BaseModel):
    name: str
    description: str
    risk: Literal["low", "medium", "high"]
    modifies_files: bool = False
    runs_shell: bool = False
    needs_network: bool = False
    requires_confirmation: bool = False
```

Default action policy:

```txt id="otp33a"
low-risk read-only actions:
  can auto-approve

medium-risk actions:
  require dry-run or preview

high-risk actions:
  require explicit confirmation

destructive actions:
  blocked unless explicitly enabled
```

Dangerous command rules:

```txt id="3d56er"
Block:
  rm -rf /
  mkfs
  shutdown
  reboot
  curl | sh
  wget | sh
  chmod -R 777

Require confirmation:
  rm
  mv
  git push
  git commit
  pip install
  npm install
  docker run
  file writes
```

---

## 17. Runtime modes

`/ai` should support modes explicitly.

```txt id="e0q1cr"
decide:
  no execution
  produce route, facts, decisions

dry_run:
  no execution
  produce proposed/approved/blocked actions

execute:
  execute approved actions only

explain:
  summarize previous AIPacket
```

Suggested commands:

```txt id="hjqbnu"
/ai <task>
  default mode: decide or dry_run

/ai --execute <task>
  execute approved safe actions

/ai --confirm <task>
  include user_confirmed=true

/decide <task>
  alias for /ai --mode decide

/dryrun <task>
  alias for /ai --mode dry_run
```

Default should be conservative:

```txt id="nuol5n"
/ai defaults to decide or dry_run, not execute.
```

---

## 18. Persistence

Store the last packet and optionally all packets.

```txt id="au7qaa"
registry["last_ai_packet"] = packet
```

Optional SQLite tables:

```txt id="il0cir"
ai_runs
ai_facts
ai_predictions
ai_rules_fired
ai_decisions
ai_actions
ai_tool_results
ai_feedback
```

This supports:

```txt id="p6xjoh"
debugging
replay
training scikit-learn
evals
audit trail
```

---

## 19. Failure rules

No silent fallback.

```txt id="r024wu"
No route:
  status = no_route

Provider fails:
  record diagnostic
  continue if non-critical

Fact extraction fails:
  use route + rules if possible
  otherwise status = needs_clarification

Risky action without confirmation:
  status = needs_confirmation

Ambiguous destructive task:
  status = needs_clarification

All providers fail:
  status = provider_error

Invalid packet:
  status = validation_failed

Tool execution fails:
  status = execution_failed
  store AIToolResult
```

The system should not do this:

```txt id="2s8vvw"
provider failed -> let LLM wing it
```

---

## 20. File layout

Suggested structure:

```txt id="yiopg6"
core/
  ai/
    __init__.py
    models.py
    provider.py
    service.py
    registry.py
    normalize.py
    validate.py
    render.py
    merge.py

    providers/
      __init__.py
      semantic_route.py
      llm_facts.py
      sklearn_predict.py
      clipspy_rules.py
      grounding_bridge.py
      solver.py
      tool_planner.py
      safety_policy.py
      execution.py
      reflection.py

    rules/
      templates.clp
      policy.clp
      routing.clp

commands/
  ai.py
  decide.py
  dryrun.py
  actions.py
  trace.py
  rules.py
  facts.py
```

---

## 21. Minimal implementation order

### Phase 1 — Packet and provider skeleton

```txt id="t2upgx"
AIPacket
AIProvider
AIProviderResult
AIService
merge_ai_provider_result()
validate_ai_packet()
```

### Phase 2 — Decide mode

```txt id="1vc9bs"
SemanticRouteProvider
LLMFactExtractorProvider
CLIPSpyRuleProvider
/ai in decide mode
registry["last_ai_packet"]
```

### Phase 3 — Introspection

```txt id="hs0ult"
/aiing
/actions
/rules
/facts
/trace
```

### Phase 4 — Dry run mode

```txt id="vaybdw"
ToolPlannerProvider
SafetyPolicyProvider
approved/blocked actions
no execution
```

### Phase 5 — Execution mode

```txt id="0y6fvl"
ExecutionProvider
read-only tools first
sandboxed shell later
confirmation gate
```

### Phase 6 — Learning and solvers

```txt id="sv9wkm"
SklearnPredictionProvider
SolverProvider
training from logs
constraint-solving workflows
```

### Phase 7 — Grounding bridge

```txt id="h9nsgo"
AIPacket can reference EvidencePacket
/ai can ask /ground for evidence
/ground remains independent
```

---

## 22. Non-goals

Do not put these into `/ai` initially:

```txt id="pgzrsp"
unbounded autonomous loops
silent shell execution
mandatory vector databases
mandatory cloud model APIs
large required agent framework
hidden prompt-only routing
automatic git push
automatic file deletion
AgentScript runner path
semantic router execution as authority
```

Keep `/ai` focused:

```txt id="ptkt5g"
route
extract
predict
reason
plan
approve
optionally execute
log
```

---

## 23. Final principle

`/ground` answers with evidence.

`/ai` decides and acts with controls.

The equivalent safety boundary is:

```txt id="aqsc60"
/ground:
  The LLM only sees grounded evidence through EvidencePacket.

/ai:
  The executor only sees approved actions through AIPacket.
```

That is the architecture worth building.
