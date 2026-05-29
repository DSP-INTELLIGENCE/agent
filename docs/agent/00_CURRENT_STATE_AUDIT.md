# Current State Audit

Known checkpoints:

```text
b3e5925 add grounding evidence packet adapter layer
0b0d983 repair active route handlers after semantic decommission
c214ad4 legacy-unwire semantic stack and repair ground usage
```

The EvidencePacket adapter layer exists:

```text
core/grounding/evidence.py
core/grounding/providers.py
core/grounding/service.py
core/grounding/__init__.py
tests/test_grounding_evidence_packet.py
```

Concepts present:

```text
EvidencePacket
EvidenceSource
EvidenceClaim
GroundingProvider
ProviderResult
GroundingService
StaticGroundingProvider
```

The failed live `/ground` EvidencePacket bridge should not be present.

Audit commands:

```bash
cd ~/Downloads/agent
git status -sb
git log --oneline --decorate -10
git diff b3e5925..HEAD -- core/agent_runtime.py
test -e tests/test_grounding_evidence_packet_runtime_bridge.py && echo "BRIDGE TEST EXISTS" || echo "bridge test absent"
```

Expected safe result:

```text
no core/agent_runtime.py diff after b3e5925
bridge test absent
```

Known repo/docs drift to audit:

```text
README may still mention /question or legacy prompt-template lanes as active.
CODEC docs must say codec ground -> /ground, not /question.
PATCH docs must match codec-patch workflow.
GROUND docs must state EvidencePacket bridge is planned unless implemented.
```
