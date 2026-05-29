"""HTML scraping helpers for the core scrape layer."""
from __future__ import annotations

from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urljoin, urlsplit

from .models import ScrapeResult
from .normalize import normalize_text, truncate_text

try:  # optional dependency
    from bs4 import BeautifulSoup  # type: ignore
except Exception:  # pragma: no cover - dependency not installed in this env
    BeautifulSoup = None  # type: ignore[assignment]

try:  # optional dependency
    import selectolax.parser as selectolax_parser  # type: ignore
except Exception:  # pragma: no cover - dependency not installed in this env
    selectolax_parser = None  # type: ignore[assignment]

try:  # optional dependency
    import trafilatura  # type: ignore
except Exception:  # pragma: no cover - dependency not installed in this env
    trafilatura = None  # type: ignore[assignment]


def extract_links(html: str, base_url: str | None = None) -> tuple[str, ...]:
    html_text = str(html or "")
    links: list[str] = []
    seen: set[str] = set()

    for candidate in _iter_links_bs4(html_text, base_url=base_url):
        if candidate not in seen:
            seen.add(candidate)
            links.append(candidate)

    if not links:
        for candidate in _iter_links_selectolax(html_text, base_url=base_url):
            if candidate not in seen:
                seen.add(candidate)
                links.append(candidate)

    if not links:
        for candidate in _iter_links_stdlib(html_text, base_url=base_url):
            if candidate not in seen:
                seen.add(candidate)
                links.append(candidate)

    return tuple(links)


def scrape_html(html: str, url: str | None = None) -> ScrapeResult:
    html_text = str(html or "")
    title = ""
    text = ""
    source = "unknown"

    trafilatura_result = _scrape_with_trafilatura(html_text, url=url)
    if trafilatura_result is not None:
        title = trafilatura_result["title"]
        text = trafilatura_result["text"]
        source = "trafilatura"
    else:
        selectolax_result = _scrape_with_selectolax(html_text, url=url)
        if selectolax_result is not None:
            title = selectolax_result["title"]
            text = selectolax_result["text"]
            source = "selectolax"
        else:
            bs4_result = _scrape_with_bs4(html_text, url=url)
            if bs4_result is not None:
                title = bs4_result["title"]
                text = bs4_result["text"]
                source = "bs4"
            else:
                fallback_result = _scrape_with_stdlib(html_text, url=url)
                title = fallback_result["title"]
                text = fallback_result["text"]
                source = "stdlib"

    cleaned_title = normalize_text(title)
    cleaned_text = truncate_text(text)
    links = extract_links(html_text, base_url=url)
    normalized_url = normalize_text(url or "")

    return ScrapeResult(
        url=normalized_url,
        title=cleaned_title,
        text=cleaned_text,
        links=links,
        source=source,
    )


def _scrape_with_trafilatura(html_text: str, *, url: str | None) -> dict[str, str] | None:
    if trafilatura is None:
        return None

    try:
        text = trafilatura.extract(
            html_text,
            url=url,
            include_comments=False,
            include_tables=False,
            favor_recall=False,
        )
    except Exception:
        return None

    if not text:
        return None

    title = ""
    try:
        extracted_metadata = trafilatura.extract_metadata(html_text, url=url)
    except Exception:
        extracted_metadata = None
    if extracted_metadata is not None:
        title = normalize_text(getattr(extracted_metadata, "title", "") or "")

    return {"title": title, "text": normalize_text(text)}


def _scrape_with_selectolax(html_text: str, *, url: str | None) -> dict[str, str] | None:
    if selectolax_parser is None:
        return None

    try:
        parser = selectolax_parser.HTMLParser(html_text)
        title_node = parser.css_first("title")
        body_node = parser.body
        title = normalize_text(title_node.text() if title_node else "")
        text = normalize_text(body_node.text(separator="\n", strip=True) if body_node else parser.text())
        if not title and not text:
            return None
        return {"title": title, "text": text}
    except Exception:
        return None


def _scrape_with_bs4(html_text: str, *, url: str | None) -> dict[str, str] | None:
    if BeautifulSoup is None:
        return None

    try:
        soup = BeautifulSoup(html_text, "html.parser")
    except Exception:
        return None

    for tag in soup(["script", "style", "noscript"]):
        tag.extract()

    title = normalize_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    body = soup.body or soup
    text = normalize_text(body.get_text("\n", strip=True))

    if not title and not text:
        return None

    return {"title": title, "text": text}


class _StdlibScrapeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._title_parts: list[str] = []
        self._in_title = False
        self._skip_depth = 0
        self._links: list[str] = []
        self._seen_links: set[str] = set()

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
            return
        if tag in {"p", "br", "div", "li", "section", "article", "header", "footer", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._parts.append("\n")

        if tag == "a":
            href = ""
            for key, value in attrs:
                if key.lower() == "href" and value:
                    href = str(value)
                    break
            raw_href = normalize_text(href)
            if raw_href and raw_href not in self._seen_links:
                self._seen_links.add(raw_href)
                self._links.append(raw_href)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag == "title":
            self._in_title = False
            return
        if tag in {"p", "div", "li", "section", "article", "header", "footer", "tr"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        text = str(data or "")
        if not text.strip():
            return
        if self._in_title:
            self._title_parts.append(text)
        else:
            self._parts.append(text)

    @property
    def title(self) -> str:
        return normalize_text("".join(self._title_parts))

    @property
    def text(self) -> str:
        return normalize_text(" ".join(self._parts))

    @property
    def links(self) -> tuple[str, ...]:
        return tuple(self._links)


def _scrape_with_stdlib(html_text: str, *, url: str | None) -> dict[str, str]:
    parser = _StdlibScrapeParser()
    try:
        parser.feed(html_text)
        parser.close()
    except Exception:
        pass
    return {"title": parser.title, "text": parser.text}


def _iter_links_bs4(html_text: str, *, base_url: str | None) -> Iterable[str]:
    if BeautifulSoup is None:
        return ()
    try:
        soup = BeautifulSoup(html_text, "html.parser")
    except Exception:
        return ()

    links: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        normalized = _normalize_http_link(anchor.get("href"), base_url=base_url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            links.append(normalized)
    return links


def _iter_links_selectolax(html_text: str, *, base_url: str | None) -> Iterable[str]:
    if selectolax_parser is None:
        return ()
    try:
        parser = selectolax_parser.HTMLParser(html_text)
        links: list[str] = []
        seen: set[str] = set()
        for node in parser.css("a[href]"):
            href = node.attributes.get("href", "")
            normalized = _normalize_http_link(href, base_url=base_url)
            if normalized and normalized not in seen:
                seen.add(normalized)
                links.append(normalized)
        return links
    except Exception:
        return ()


def _iter_links_stdlib(html_text: str, *, base_url: str | None) -> Iterable[str]:
    parser = _StdlibScrapeParser()
    try:
        parser.feed(html_text)
        parser.close()
    except Exception:
        pass
    links: list[str] = []
    seen: set[str] = set()
    for raw_link in parser.links:
        normalized = _normalize_http_link(raw_link, base_url=base_url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            links.append(normalized)
    return tuple(links)


def _normalize_http_link(href: str | None, *, base_url: str | None) -> str | None:
    raw = normalize_text(href or "")
    if not raw:
        return None
    candidate = urljoin(base_url or "", raw) if base_url else raw
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc:
        return None
    normalized = parsed._replace(fragment="").geturl()
    return normalized
