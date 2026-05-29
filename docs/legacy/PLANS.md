Here is the build plan that uses the **existing Agent core as the foundation** and makes `codec` work as the encoder/decoder layer instead of rewriting Agent again.

Agent already defines the lane architecture: instructions go through lane selection, registry/capability validation, lane runtime, optional search/scrape/grounding/assembly, and then LLM response only when the lane permits it. It also states “No lane, no LLM,” and semantic routing is candidate generation only: semantic router proposes, registry authorizes, runtime executes. ([GitHub][1])

# Goal

```text
codec = encoder + decoder

encoder:
  use Agent core lane/route/ground/search/scrape/LLM infrastructure
  build a ResearchPacket

decoder:
  use Agent core LLM front door / response policy
  write final answer from ResearchPacket only
```

`codec` should not rebuild Agent’s switchboard, patch system, CLI runtime, lane registry, capability validation, or LLM client. It should import/adapt them.

---

# 1. Repo relationship

Use two repos:

```text
agent/
  existing foundation
  owns lanes, validators, registries, runtime contracts, patcher, LLM front door

codec/
  encoder-decoder package
  imports Agent core through a thin adapter
  builds ResearchPacket
  decodes ResearchPacket to final answer
```

Do **not** copy all of `agent/core` into `codec`.

Instead create:

```text
codec/adapters/agent_core.py
```

That adapter is the only place `codec` touches Agent internals.

---

# 2. Dependency direction

```text
codec
  → imports selected agent.core modules
  → never imports agent.py
  → never imports agent-cli.py as a runtime dependency
```

Allowed Agent imports:

```text
core.command_registry
core.command_registry_loader
core.lane_capability_validator
core.semantic_route_catalog
core.semantic_route_selection
core.semantic_route_threshold
core.semantic_route_diagnostics
core.semantic_route_handoff
core.lane_invocation
core.llm_open_webui_client
core.llm_front_door / llm_runtime_front_door
core.ground/*
core.search/*
core.web/*
core.scrape/*
core.response_policy/*
```

Avoid:

```text
agent.py
agent-cli.py
terminal loop
batch shell frontends
patch runner except for creating/applying patches
anything that directly handles terminal I/O
```

---

# 3. Codec package layout

Move from top-level loose scripts toward:

```text
codec/
  __init__.py
  models.py
  encoder.py
  decoder.py
  router.py
  lanes.py
  packet.py
  privacy.py

  adapters/
    __init__.py
    agent_core.py
    openwebui.py

  collectors/
    __init__.py
    ground.py
    wikipedia.py
    dictionary.py
    web_search.py
    scrape.py
    files.py
    corpus.py

  tests/
    test_encoder_packet.py
    test_decoder.py
    test_agent_core_adapter.py
    test_router_policy.py
    golden/
      encoder_question_empty.json
      encoder_question_grounded.json
      decoder_empty_refusal.txt
```

Keep `run.py` thin:

```text
normalize input
→ codec.encoder.encode()
→ codec.decoder.decode()
→ print route/evidence/debug output
```

---

# 4. Core data contract: ResearchPacket

Create one stable packet model.

```python
@dataclass(frozen=True)
class ResearchPacket:
    schema_version: str
    input: dict
    route: dict
    route_candidates: list[dict]
    lane_contract: dict | None
    capability_decision: dict
    fired_lanes: list[dict]
    evidence: dict
    evidence_summary: dict
    privacy: dict
    decoder_policy: dict
    metadata: dict
```

Stable fields:

```text
schema_version
input.raw
input.normalized
route.selected_lane
route.source
route.confidence
route.reason
route.candidates
capability_decision
evidence.ground
evidence.wikipedia
evidence.dictionary
evidence.web_search
evidence.scrape
evidence.files
evidence.corpus
evidence.lane_outputs
privacy
decoder_policy
metadata.statement
```

The packet is the **only** decoder input.

---

# 5. Adapter milestone: import Agent core cleanly

Create:

```text
codec/adapters/agent_core.py
```

Responsibilities:

```text
load Agent command registry
read lane metadata
run Agent capability validator
call Agent semantic route control-plane objects when available
call Agent LLM front door
call Agent ground/search/web/scrape modules when available
normalize Agent outputs into Codec ResearchPacket fields
```

Example adapter surface:

```python
class AgentCoreAdapter:
    def load_registry(self) -> CommandRegistry: ...
    def lane_contract(self, lane: str) -> dict: ...
    def validate_capabilities(self, lane: str, requested: dict) -> dict: ...
    def semantic_candidates(self, text: str) -> list[dict]: ...
    def threshold_decision(self, candidates: list[dict]) -> dict: ...
    def diagnostics_summary(self, candidates: list[dict]) -> dict: ...
    def handoff_assessment(self, diagnostics: dict, threshold: dict) -> dict: ...
    def call_llm(self, messages: list[dict]) -> str: ...
```

This keeps `codec` from becoming a second Agent.

---

# 6. Router plan

Do not make `codec.router` own the whole truth.

Router should do:

```text
plain/slash input
→ Agent semantic route candidate model if available
→ Agent threshold decision if available
→ policy normalization
→ selected broad encoder lane
```

Selection rule:

```text
semantic-router proposes
Agent registry/capability validator authorizes
Codec encoder decides what research to collect
```

For natural language lookup/search/factual/person/contact input:

```text
selected lane = /question or /grounded_answer
```

Not:

```text
/find
/scrape
/ls
/tree
```

unless slash-explicit or input shape is valid.

---

# 7. Encoder plan

`codec.encoder.encode(input)` is the main build target.

Encoder flow:

```text
1. normalize input
2. get route candidates
3. validate lane using Agent core
4. select encoder mode
5. build ground plan
6. collect all evidence channels
7. fire selected lane(s)
8. attach lane outputs
9. compute evidence summary
10. compute privacy/safety flags
11. assemble ResearchPacket
```

Important: evidence collection is universal.

Every packet includes:

```text
ground
wikipedia
dictionary
web_search
scrape
files
corpus
lane_outputs
```

Even if a collector is disabled or not implemented, it must return a status.

---

# 8. Evidence collector plan

Each collector returns the same shape:

```python
{
  "status": "ok|none|empty|not_implemented|network_disabled|error",
  "query": "...",
  "items": [],
  "metadata": {}
}
```

## 8.1 Ground collector

Use Agent’s existing grounding modules if possible.

```text
collector: codec.collectors.ground
adapter: AgentCoreAdapter.ground_plan()
```

Output:

```text
query
source_plan
required_terms
privacy_flags
freshness_need
confidence_need
```

## 8.2 Wikipedia collector

Can stay native in `codec` initially because it is simple.

```text
network gated
summary endpoint
normalized title
stable status
```

Later: replace with Agent web/search adapter if Agent owns HTTP policy.

## 8.3 Dictionary collector

Start with local/simple dictionary interface:

```text
local word list / glossary / wiktionary adapter later
```

Do not block the packet if missing.

## 8.4 Web search collector

Do **not** invent this. Use Agent core search/web if available.

Adapter priority:

```text
1. Agent core search module
2. Agent core web module
3. Open WebUI search if exposed
4. configured external search backend
5. status=not_configured
```

## 8.5 Scrape collector

Use Agent core scrape module if available.

Rules:

```text
only explicit URL
network-gated
return extracted readable text
do not search web here
```

## 8.6 Files collector

Use Agent’s `/read`, `/tree`, `/find` semantics only when safe.

Natural language lookup should not trigger local file find as the selected lane, but the encoder may still collect local file evidence if configured.

## 8.7 Corpus collector

Define contract first.

```text
status=not_configured
items=[]
```

Later sources:

```text
Agent memory
local docs
vector index
SQLite corpus
project notes
knowledge base
```

---

# 9. Lane firing plan

The encoder should not “answer” through the lane. It fires lanes to add structured output.

Current behavior:

```text
fire selected lane only
```

Future behavior:

```text
fire selected lane
fire supporting lanes when policy allows
```

Examples:

```text
/question
  fires question lane
  evidence collectors already ran

/web
  fires web lane
  web_search collector should populate results

/scrape URL
  fires scrape lane
  scrape collector also populates evidence

/read README.md
  fires read lane
  file content becomes lane output evidence
```

---

# 10. Decoder plan

Decoder must use Agent LLM front door, not a separate invented client long-term.

Initial:

```text
codec.decoder → AgentCoreAdapter.call_llm()
```

Fallback:

```text
local Ollama/Open WebUI adapter only if Agent adapter unavailable
```

Decoder rules:

```text
ResearchPacket in
final answer out
no routing
no searching
no scraping
no file reads
no tool calls
no claims not in evidence
do not mention packet/router/lane/runtime
```

Decoder policy should be explicit:

```python
decoder_policy = {
    "use_evidence_only": True,
    "empty_evidence_behavior": "cannot_verify",
    "private_contact_policy": "require_public_business_evidence",
    "forbid_runtime_mentions": True,
}
```

---

# 11. Privacy / contact-info plan

Add a privacy classifier in encoder.

```python
privacy = {
    "person_lookup": bool,
    "contact_info_requested": bool,
    "address_requested": bool,
    "phone_requested": bool,
    "email_requested": bool,
    "requires_public_business_evidence": bool,
}
```

Rules:

```text
private-person address/phone/email requires strong public business/contact evidence
otherwise decoder refuses or says not verified
```

This belongs in the encoder packet so the decoder has no ambiguity.

---

# 12. Test plan

## 12.1 Adapter tests

```text
AgentCoreAdapter imports without terminal side effects
registry loads
lane contract can be read
capability validator returns deterministic decision
LLM adapter can be mocked
```

## 12.2 Router tests

```text
hello → prompt
what is cheese → question
lookup phone number for person → question
search github for synth → question or web, not find
where is unknown place → question, not scrape
/read README.md → read via slash
/scrape https://example.com → scrape via slash
```

## 12.3 Encoder tests

```text
ResearchPacket includes all evidence channels
network disabled gives stable statuses
selected lane output attached
empty evidence does not become grounded
privacy flags set for contact lookup
route candidates preserved
```

## 12.4 Decoder tests

```text
empty evidence → cannot verify
grounded evidence → answer from evidence
private contact request without public evidence → refuse/not verify
no packet/router/runtime wording leaks
```

## 12.5 Golden tests

```text
tests/golden/research_packet_empty_question.json
tests/golden/research_packet_contact_lookup.json
tests/golden/research_packet_file_read.json
tests/golden/decoder_empty_response.txt
```

---

# 13. Milestone sequence

## Milestone 1 — Repair package layout

Goal:

```text
codec imports and runs
```

Tasks:

```text
valid Python modules
codec/ package directory
thin run.py
tests import cleanly
```

Commit:

```text
repair codec package layout
```

---

## Milestone 2 — Agent core adapter

Goal:

```text
codec can use Agent core without copying foundation
```

Tasks:

```text
codec/adapters/agent_core.py
load registry
read lane contracts
call capability validator
mockable LLM front door
no terminal side effects
```

Commit:

```text
add agent core adapter
```

---

## Milestone 3 — ResearchPacket model

Goal:

```text
stable encoder output
```

Tasks:

```text
ResearchPacket dataclass
to_dict()
JSON renderer
schema_version
stable fields
golden test
```

Commit:

```text
define research packet model
```

---

## Milestone 4 — Encoder v1

Goal:

```text
route + validate + collect all channels + fire selected lane
```

Tasks:

```text
encode()
route candidates
capability decision
all evidence channels
lane output attached
privacy flags
```

Commit:

```text
build encoder research packet
```

---

## Milestone 5 — Decoder v1

Goal:

```text
packet → answer only
```

Tasks:

```text
Agent LLM adapter
decoder prompt
empty evidence refusal
private contact refusal
no runtime wording leaks
```

Commit:

```text
build evidence bound decoder
```

---

## Milestone 6 — Agent search/web/scrape integration

Goal:

```text
real evidence, not stubs
```

Tasks:

```text
wire Agent ground/search/web/scrape modules through adapter
collector status normalization
network policy
tests with mocked Agent collectors
```

Commit:

```text
wire agent evidence collectors
```

---

## Milestone 7 — CLI and debug

Goal:

```text
usable local codec CLI
```

Tasks:

```text
run.py --text
run.py --debug
route switch display
evidence status display
packet JSON output
```

Commit:

```text
add codec cli debug output
```

---

## Milestone 8 — Agent integration seam

Goal:

```text
Agent can call codec
```

Tasks:

```text
agent /question invokes codec encoder
agent receives ResearchPacket
agent invokes decoder or uses agent LLM front door
result artifact
no plain text bypass
```

Commit:

```text
add codec integration seam
```

---

# 14. Patch workflow for all milestones

Use the existing Agent patch system, not custom ZIPs.

Create branch:

```bash
git checkout -b codec/agent-core-adapter
```

After edits:

```bash
git status --short
git diff
git diff --stat
```

Package with Agent’s patch tool:

```bash
python /path/to/agent/scripts/make_patch_package.py \
  --repo . \
  --output /tmp/codec-agent-core-adapter.zip \
  --name "add agent core adapter" \
  --description "Use Agent core registry, capability validation, and LLM front door from codec." \
  --risk medium \
  --allowed-path codec/ \
  --allowed-path tests/ \
  --allowed-path run.py \
  --allowed-path README.md
```

Apply/verify with Agent patch runner:

```bash
python /path/to/agent/scripts/agent_patch_runner.py \
  /tmp/codec-agent-core-adapter.zip \
  --repo . \
  --full-test "python -m pytest -q"
```

Commit:

```bash
git add .
git commit -m "add agent core adapter"
git push -u origin codec/agent-core-adapter
gh pr create --fill
```

Inspect:

```bash
gh pr view --web
```

Revert:

```bash
git revert HEAD
```

---

# 15. What not to do

Do not rebuild these in `codec`:

```text
Agent command registry
AgentScript runner
patch runner
terminal frontend
switchboard
full LLM provider system
full scrape/search/web stacks
capability validator
semantic route threshold/handoff models
```

Use Agent core for those.

Only build what is missing:

```text
ResearchPacket
Encoder orchestration
Decoder over ResearchPacket
AgentCoreAdapter normalization layer
```

---

# 16. Final target

```text
agent /question "what is X?"
→ Agent validates lane
→ codec.encode()
    semantic route candidates
    ground plan
    wikipedia
    dictionary
    web_search
    scrape
    files
    corpus
    lane outputs
    privacy flags
    ResearchPacket
→ codec.decode()
    final evidence-bound answer
→ Agent displays result/artifact
```

That gives you the architecture you wanted without throwing away the Agent core already built.

[1]: https://github.com/DSP-INTELLIGENCE/agent "GitHub - DSP-INTELLIGENCE/agent · GitHub"
