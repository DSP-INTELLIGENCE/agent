# Agent Architecture Roadmap

This roadmap is repo-local state for continuing the Agent architecture work from the repository itself.

## Completed Stack

- semantic route catalog fixtures
- semantic route definitions
- semantic router adapter skeleton
- semantic route selection
- route audit artifact
- route dry-run `/route inspect`
- route replay fixtures
- catalog ambiguity checks
- route inspect JSON golden tests
- route inspect markdown golden tests
- diagnostics summary
- diagnostics golden tests
- threshold policy
- threshold golden tests
- handoff assessment
- handoff golden tests
- LaneInvocation model
- LaneInvocation golden tests
- preserve input text through diagnostics, handoff, and LaneInvocation
- AgentScript v1 data model
- AgentScript golden tests
- AgentScript structural validator
- AgentScript registry validator

## Next Milestones

1. Add AgentScript capability validator
2. Add AgentScript validation pipeline
3. Add AgentScript validation pipeline golden tests
4. Compile LaneInvocation to AgentScript for `/read`
5. Compile LaneInvocation to AgentScript for `/tree`
6. Compile LaneInvocation to AgentScript for `/find`
7. Add compiler golden tests
8. Add read-only AgentScript runner MVP for `/read`
9. Add runner MVP for `/tree` and `/find`
10. Add runner report artifact
11. Add assembly packet model

## Architecture Rules

- semantic routing proposes
- registry authorizes
- threshold and handoff decide readiness
- LaneInvocation describes one trusted lane call
- AgentScript makes intended execution inspectable
- validators validate
- compiler emits script text
- runner is the only execution boundary
- LLM composes only after assembly

## Hard Boundaries

- no hidden LLM fallback
- no lane, no LLM
- no runtime execution from semantic routing
- no runtime execution from LaneInvocation
- no runtime execution from AgentScript parser
- no runtime execution from validators
- no runtime execution from compiler
- no shell runner yet
- no patch runner yet
- no web/scrape runner yet
- no mutation runner yet
- no `agent.py` changes unless explicitly scoped
- `agent-cli.py` stays thin
- no plugins, tools abstraction, or switch matrix revival

## Milestone Sequence

1. Semantic routing proposals and audit artifacts
2. Deterministic `/route inspect` dry-run and replay coverage
3. Diagnostics, threshold, and handoff control-plane objects
4. LaneInvocation as the first trusted lane-call contract
5. Preserve input text through diagnostics, handoff, and LaneInvocation
6. AgentScript parse/render model
7. AgentScript structural validation
8. AgentScript registry validation
9. AgentScript capability validation
10. AgentScript validation pipeline
11. AgentScript compiler for read-only lanes
12. AgentScript compiler golden tests
13. Read-only AgentScript runner MVP
14. Runner expansion for tree and find
15. Runner report artifact
16. Assembly packet model

## Guidance

- prefer small milestones
- add code and tests together
- add golden tests after new public contracts
- do not combine compiler and runner
- do not combine registry validation and capability validation
- do not make the semantic-router package required
- keep semantic-router package research on research branches only

