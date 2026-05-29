# Ground EvidencePacket Plan

Goal:

```text
/ground consumes and produces EvidencePacket
```

Provider flow:

```text
Wikipedia / Web / Scrape / Local docs / Repo files / Vector stores
  -> GroundingProvider
  -> ProviderResult
  -> EvidencePacket
  -> /ground LLM context
```

Runtime target:

```text
/ground <question>
  -> normalize query
  -> collect provider results
  -> assemble EvidencePacket
  -> registry["last_evidence_packet"] = packet
  -> packet.render_answer_context()
  -> grounded LLM synthesis
```

Display commands:

```text
/grounding -> packet-first diagnostics, legacy fallback only
/sources   -> packet-first sources, legacy fallback only
```

Failure rules:

```text
provider fails -> continue, record diagnostic
all providers fail -> no_evidence
ambiguous query -> ambiguous
weak evidence -> cite and mark confidence
no evidence -> no raw /prompt fallback
```

Optional providers later:

```text
wikipedia-api
trafilatura / bs4
crawl4ai / firecrawl
tavily-python / exa
PyGithub / GitPython
tree-sitter
llama-index
lancedb / qdrant
ragas / deepeval
```

No API-key dependency by default.
