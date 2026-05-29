"""URL fetching primitives for the core web engine."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlsplit

from .extractor import extract_html
from .models import WebExtractResult, WebFetchResult

try:  # optional dependency
    import httpx  # type: ignore
except Exception:  # pragma: no cover - dependency not installed in this env
    httpx = None  # type: ignore[assignment]


DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
DEFAULT_USER_AGENT = "agent-web/0.1"


class WebFetchError(ValueError):
    pass


@dataclass(frozen=True)
class _RawFetchResponse:
    final_url: str
    status_code: int
    headers: dict[str, str]
    body: bytes
    content_type: str


def fetch_url(url: str) -> WebFetchResult:
    normalized = _validate_http_url(url)
    raw = _perform_fetch(
        normalized,
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes=DEFAULT_MAX_RESPONSE_BYTES,
        user_agent=DEFAULT_USER_AGENT,
    )

    text = _decode_bytes(raw.body, raw.content_type)
    extracted: WebExtractResult | None = None
    title = ""
    page_text = text.strip()
    if _looks_like_html(raw.content_type, text):
        extracted = extract_html(text, url=raw.final_url)
        title = extracted.title
        page_text = extracted.text

    return WebFetchResult(
        url=normalized,
        final_url=raw.final_url,
        status_code=raw.status_code,
        headers=dict(raw.headers),
        content=raw.body,
        content_type=raw.content_type,
        title=title,
        text=page_text,
        extracted=extracted,
    )


def _validate_http_url(url: str) -> str:
    text = str(url or "").strip()
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"}:
        raise WebFetchError("fetch_url only accepts http(s) URLs")
    if not parsed.netloc:
        raise WebFetchError("fetch_url requires a valid http(s) URL")
    return text


def _perform_fetch(
    url: str,
    *,
    timeout_seconds: int,
    max_response_bytes: int,
    user_agent: str,
) -> _RawFetchResponse:
    if httpx is not None:
        return _perform_fetch_httpx(
            url,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            user_agent=user_agent,
        )
    return _perform_fetch_urllib(
        url,
        timeout_seconds=timeout_seconds,
        max_response_bytes=max_response_bytes,
        user_agent=user_agent,
    )


def _perform_fetch_httpx(
    url: str,
    *,
    timeout_seconds: int,
    max_response_bytes: int,
    user_agent: str,
) -> _RawFetchResponse:
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        with httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers=headers,
        ) as client:
            with client.stream("GET", url) as response:
                body = _read_response_body(response.iter_bytes(), max_response_bytes=max_response_bytes)
                response_headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
                return _RawFetchResponse(
                    final_url=str(response.url),
                    status_code=int(response.status_code),
                    headers=response_headers,
                    body=body,
                    content_type=response_headers.get("content-type", ""),
                )
    except Exception as exc:
        raise WebFetchError(f"fetch_url failed for {url}: {exc}") from exc


def _perform_fetch_urllib(
    url: str,
    *,
    timeout_seconds: int,
    max_response_bytes: int,
    user_agent: str,
) -> _RawFetchResponse:
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    request = urlrequest.Request(url, headers=headers, method="GET")
    try:
        with urlrequest.urlopen(request, timeout=timeout_seconds) as response:
            body = _read_response_body(_iter_response_chunks(response), max_response_bytes=max_response_bytes)
            response_headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
            return _RawFetchResponse(
                final_url=str(response.geturl()),
                status_code=int(getattr(response, "status", response.getcode() or 0)),
                headers=response_headers,
                body=body,
                content_type=response_headers.get("content-type", ""),
            )
    except urlerror.HTTPError as exc:
        body = _read_response_body(_iter_error_chunks(exc), max_response_bytes=max_response_bytes)
        response_headers = {str(k).lower(): str(v) for k, v in getattr(exc, "headers", {}).items()}
        return _RawFetchResponse(
            final_url=str(getattr(exc, "url", url)),
            status_code=int(getattr(exc, "code", 0) or 0),
            headers=response_headers,
            body=body,
            content_type=response_headers.get("content-type", ""),
        )
    except Exception as exc:
        raise WebFetchError(f"fetch_url failed for {url}: {exc}") from exc


def _iter_response_chunks(response) -> Iterable[bytes]:  # type: ignore[no-untyped-def]
    while True:
        chunk = response.read(64 * 1024)
        if not chunk:
            break
        yield chunk


def _iter_error_chunks(error: urlerror.HTTPError) -> Iterable[bytes]:
    while True:
        chunk = error.read(64 * 1024)
        if not chunk:
            break
        yield chunk


def _read_response_body(chunks: Iterable[bytes], *, max_response_bytes: int) -> bytes:
    data = bytearray()
    for chunk in chunks:
        if not chunk:
            continue
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8")
        data.extend(chunk)
        if len(data) > max_response_bytes:
            raise WebFetchError(
                f"response body exceeded limit of {max_response_bytes} bytes"
            )
    return bytes(data)


def _decode_bytes(body: bytes, content_type: str) -> str:
    charset = _charset_from_content_type(content_type) or "utf-8"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _charset_from_content_type(content_type: str) -> str:
    match = re.search(r"charset=([^\s;]+)", str(content_type or ""), flags=re.I)
    return match.group(1).strip().strip('"').strip("'") if match else ""


def _looks_like_html(content_type: str, text: str) -> bool:
    content_type_text = str(content_type or "").lower()
    if "html" in content_type_text:
        return True
    sample = str(text or "").lstrip().lower()
    return sample.startswith("<!doctype html") or sample.startswith("<html") or "<html" in sample[:1024]
