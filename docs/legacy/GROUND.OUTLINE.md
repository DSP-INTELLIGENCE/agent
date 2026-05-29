## `/ground` adapter outline

### Goal

Make `/ground` consume one stable payload:

```text
EvidencePacket
```

Everything else becomes an adapter.

```text
Wikipedia
Web search
Scrapers
Local docs
Repo files
Vector stores
Future APIs
        ↓
GroundingProvider
        ↓
ProviderResult
        ↓
EvidencePacket
        ↓
/ground LLM context
```

### Core contract

```python
class GroundingProvider(Protocol):
    name: str

    @property
    def available(self) -> bool:
        ...

    def collect(
        self,
        query: str,
        *,
        normalized_query: str = "",
        targets: list[str] | None = None,
        profile: str = "general_reference",
    ) -> ProviderResult:
        ...
```

### Provider output

```python
@dataclass
class ProviderResult:
    provider: str
    ok: bool
    sources: list[EvidenceSource]
    claims: list[EvidenceClaim]
    diagnostics: dict = field(default_factory=dict)
    error: str | None = None
```

### Runtime flow

```python
def handle_ground(question: str, registry: dict) -> str:
    normalized_query = normalize_query(question)
    targets = extract_targets(normalized_query)

    service = build_default_grounding_service()

    packet = service.collect(
        query=question,
        normalized_query=normalized_query,
        targets=targets,
        profile="general_reference",
    )

    registry["last_evidence_packet"] = packet

    if not packet.ok:
        return packet.render_failure()

    return llm.grounded_answer(
        question=question,
        context=packet.render_answer_context(),
    )
```

### Registry

```python
def build_default_grounding_service() -> GroundingService:
    providers = [
        WikipediaProvider.optional(),
        FetchExtractProvider.optional(),
        SearchProvider.optional(),
        LocalDocsProvider.optional(),
        RepoDocsProvider.optional(),
        VectorStoreProvider.optional(),
    ]

    return GroundingService(
        providers=[p for p in providers if p and p.available]
    )
```

### PyPI adapters later

```text
wikipedia-api          -> WikipediaProvider
trafilatura / bs4      -> FetchExtractProvider
crawl4ai / firecrawl   -> FetchExtractProvider
tavily-python / exa-py -> SearchProvider
PyGithub / GitPython   -> RepoDocsProvider
tree-sitter            -> CodeChunkProvider
llama-index            -> VectorStoreProvider / LocalDocsProvider
lancedb / qdrant       -> Vector backend
ragas / deepeval       -> Grounding eval harness
```

### `/grounding` and `/sources`

```python
def handle_grounding(registry: dict) -> str:
    packet = registry.get("last_evidence_packet")
    if packet:
        return packet.render_diagnostics()

    return render_legacy_grounding(registry)


def handle_sources(registry: dict) -> str:
    packet = registry.get("last_evidence_packet")
    if packet:
        return packet.render_sources()

    return render_legacy_sources(registry)
```

### Failure rules

```text
One provider fails    -> continue, add diagnostic
All providers fail    -> packet.status = "no_evidence"
Ambiguous query       -> packet.status = "ambiguous"
Weak evidence         -> low confidence, still cite it
No evidence           -> no raw /prompt fallback
```

### Phase 2 patch scope

```text
1. Wire /ground to GroundingService
2. Store registry["last_evidence_packet"]
3. Feed only packet.render_answer_context() to LLM
4. Make /grounding packet-first
5. Make /sources packet-first
6. Preserve legacy fallback only for display commands
7. Add tests for no raw fallback
```
