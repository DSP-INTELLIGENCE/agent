# Web Lane

The web lane is the core fetch-and-extract engine for future `/web` routing.

## Current Scope

This slice provides local engine primitives and inspect-only routing:

- `core/scrape` owns reusable deterministic extraction and normalization logic
- `core/web.extractor` is a thin adapter over `core/scrape`
- URL fetching with bounded timeouts and response size limits
- HTML extraction into deterministic plain text
- `/web fetch <url>` is routed through `agent-cli.py`
- `/web extract <url>` is routed through `agent-cli.py`
- `/search web <query>` is routed through `agent-cli.py`
- optional `/web search <query>` is routed through `agent-cli.py`
- optional cache/report artifacts live under `reports/web-cache/`
- no browser automation
- no JavaScript execution
- no crawl behavior
- search is inspect-only and bounded
- cache writes are inspect-only and local

## Dependencies

The intended web stack is listed in `requirements/web.txt`:

- `httpx`
- `trafilatura`
- `beautifulsoup4`
- `selectolax`
- `ddgs`

## Safety Defaults

- timeout: 20 seconds
- maximum response size: 5 MB
- explicit user agent
- only `http://` and `https://` URLs are accepted

## Extraction Order

Preferred extraction order:

1. `trafilatura`
2. `selectolax` for simple fallback parsing
3. BeautifulSoup title/body extraction
4. a minimal stdlib HTML fallback if the optional packages are unavailable

## Next Step

The web lane still has no crawl, browser automation, JavaScript execution, or autonomous navigation. Search stays inspect-only and bounded, with no automatic result fetching or follow-up crawling. Cache artifacts are local and write-only; there is no automatic cache replay or background indexing.
