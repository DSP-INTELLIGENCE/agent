from __future__ import annotations

import html
import ipaddress
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

from core.constants import *

# HELPERS
# ============================================================

def now_str() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def truncate_text(text: str, limit: int) -> str:
    text = str(text or "")
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n\n[TRUNCATED]"


def tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_:/.-]{2,}", str(text or "").lower())


def jaccard_score(a: List[str], b: List[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(1, len(sa | sb))


def safe_json_loads(text: str) -> Optional[Any]:
    try:
        return json.loads(text)
    except Exception:
        return None


def as_json_text(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def merge_config_dict(defaults: Dict[str, Any], loaded: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(defaults)
    if isinstance(loaded, dict):
        for key, value in loaded.items():
            out[key] = value
    return out


def write_json_file_if_missing(path: Path, defaults: Dict[str, Any]) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(defaults, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def load_json_file_or_default(path: Path, defaults: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        write_json_file_if_missing(path, defaults)
        return dict(defaults)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(defaults)
    return merge_config_dict(defaults, data if isinstance(data, dict) else {})



def extract_first_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned.strip(), flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned.strip()).strip()
    direct = safe_json_loads(cleaned)
    if isinstance(direct, dict):
        return direct

    start = cleaned.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = cleaned[start : i + 1]
                data = safe_json_loads(candidate)
                return data if isinstance(data, dict) else None
    return None


def is_probably_url(text: str) -> bool:
    try:
        parsed = urlparse(str(text or ""))
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def normalize_url(url: str) -> str:
    url = str(url or "").strip()
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if not url.startswith(("http://", "https://")):
        return ""
    return url


def is_private_or_local_url(url: str) -> bool:
    try:
        parsed = urlparse(str(url or ""))
        host = (parsed.hostname or "").strip().lower()
        if not host:
            return True
        if host in {"localhost", "0.0.0.0"}:
            return True
        if host.endswith(".local"):
            return True
        try:
            ip = ipaddress.ip_address(host)
            return bool(
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            )
        except ValueError:
            return False
    except Exception:
        return True


def validate_public_fetch_url(url: str, *, allow_private: bool = False) -> str:
    normalized = normalize_url(url)
    if not normalized:
        raise RuntimeError("web.fetch requires a valid http(s) URL")
    if is_private_or_local_url(normalized) and not allow_private:
        raise RuntimeError(
            "Refusing to fetch private/local URL by default. "
            "Enable allow_private_url_fetch only if you trust the request."
        )
    return normalized


def decode_duckduckgo_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "uddg" in qs and qs["uddg"]:
        return unquote(qs["uddg"][0])
    return url


def coerce_int(value: Any, default: int, min_value: Optional[int] = None, max_value: Optional[int] = None) -> int:
    try:
        out = int(value)
    except Exception:
        out = default
    if min_value is not None:
        out = max(min_value, out)
    if max_value is not None:
        out = min(max_value, out)
    return out


def domain_from_url(url: str) -> str:
    try:
        return urlparse(str(url or "")).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def source_priority_score(url: str) -> int:
    domain = domain_from_url(url)
    for index, trusted in enumerate(TRUSTED_SOURCE_PRIORITY):
        if trusted in domain:
            return index
    return len(TRUSTED_SOURCE_PRIORITY) + 10


def has_grounding_text(text: str, min_chars: int = 120) -> bool:
    text = clean_text(text)
    return bool(text) and len(text) >= min_chars


def looks_like_factual_lookup(text: str) -> bool:
    lowered = clean_text(text).lower()
    if not lowered:
        return False
    # Current-news phrases need live search, not the general grounding path.
    if re.search(r"\b(?:current\s+news|latest\s+news|today'?s\s+news|today\s+news|headlines|breaking\s+news|news\s+stories|top\s+news)\b", lowered):
        return False
    if lowered.startswith(FACTUAL_LOOKUP_PREFIXES):
        return True
    factual_markers = [
        " imdb", " wikipedia", " wiki", " movie", " film", " director", " cast",
        " release date", " born", " died", " founded", " latest", " current",
        " docs", " documentation", " official", " source",
    ]
    return any(marker in f" {lowered}" for marker in factual_markers)


def format_search_results_for_context(data: Dict[str, Any]) -> str:
    results = data.get("results") or []
    lines = [f"Search query: {data.get('query', '')}", f"Backend: {data.get('backend', '')}", "", "Results:"]
    for item in results:
        lines.append(
            f"{item.get('index', '')}. {item.get('title', '')}\n"
            f"URL: {item.get('url', '')}\n"
            f"Snippet: {item.get('snippet', '')}\n"
        )
    return "\n".join(lines)


def format_memory_results_for_context(query: str, results: List[Dict[str, Any]]) -> str:
    lines = [f"Memory query: {query}", "", "Memory results:"]
    for item in results:
        lines.append(
            f"- {item.get('title', '')} (score: {item.get('score', '')})\n"
            f"  {item.get('text', '')}"
        )
    return "\n".join(lines)


def compact_search_snippets(search_data: Optional[Dict[str, Any]]) -> str:
    if not isinstance(search_data, dict):
        return ""
    parts: List[str] = []
    for item in search_data.get("results", []) or []:
        parts.append(f"{item.get('title', '')}\n{item.get('url', '')}\n{item.get('snippet', '')}")
    return clean_text("\n".join(parts))


def readable_link_list(links: List[Dict[str, str]], limit: int = 25) -> str:
    lines = []
    for item in links[:limit]:
        lines.append(f"{item.get('index')}. {item.get('text')}\n   {item.get('url')}")
    return "\n".join(lines)


def terminal_timestamp(enabled: bool = False) -> str:
    if not enabled:
        return ""
    return datetime.now().strftime("[%H:%M:%S] ")


def clean_terminal_chunk(text: Any) -> str:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n")


def compact_status_line(label: str, text: Any, *, timestamp: bool = False) -> str:
    prefix = terminal_timestamp(timestamp)
    text = clean_text(text)
    return f"{prefix}[{label}] {text}\n"



def terminal_block(label: str, text: Any, *, timestamp: bool = False) -> str:
    prefix = terminal_timestamp(timestamp)
    body = clean_terminal_chunk(text).strip()
    if not body:
        return f"{prefix}[{label}]\n"
    return f"{prefix}[{label}]\n{body}\n"

# ============================================================

def looks_like_contextual_followup(text: str) -> bool:
    lowered = clean_text(text).lower()
    if not lowered:
        return False

    # Prompt/dataset blocks often contain words like "that", "it", or "they",
    # but they are not contextual follow-up requests.
    dataset_markers = (
        "instruction:",
        "input:",
        "output:",
        "keywords:",
        "genre:",
        "narrative:",
        "main theme:",
        "positive_prompt:",
        "negative_prompt:",
        "hashtags:",
        "visualtags:",
        "title:",
        "description:",
    )
    if any(marker in lowered for marker in dataset_markers):
        return False

    followup_starts = (
        "it ",
        "that ",
        "this ",
        "they ",
        "them ",
        "he ",
        "she ",
        "the page ",
        "the result ",
        "the source ",
        "the link ",
        "the film ",
        "the movie ",
        "the short ",
        "the repo ",
        "the repository ",
        "the docs ",
        "the documentation ",
        "the package ",
        "the pypi page ",
        "the install page ",
        "who directed",
        "who starred",
        "who stars",
        "what was the cast",
        "what is the cast",
        "where is the repo",
        "where is the repository",
        "where are the docs",
        "where is the documentation",
        "where is the package",
        "where is the pypi",
        "where is the pypi page",
        "where can i install",
        "how do i install it",
        "install it",
        "package page",
        "pypi page",
        "what did that say",
        "what did it say",
        "summarize that",
        "summarize it",
        "open that",
        "follow that",
    )

    return lowered.startswith(followup_starts)

def infer_search_answer_profile(user_text: str, query: str = "") -> str:
    lowered = f"{user_text} {query}".lower()
    if any(x in lowered for x in ["imdb", "movie", "film", "cast", "director", "letterboxd", "tmdb"]):
        return "film_lookup"
    if any(x in lowered for x in ["docs", "documentation", "api", "github", "python", "package", "library", "repository", "repo"]):
        return "software_docs"
    if any(x in lowered for x in ["wikipedia", "wiki", "encyclopedia"]):
        return "reference_lookup"
    return "general_search"


def extract_search_fact_hints(search_data: Dict[str, Any], *, limit: int = 3) -> str:
    results = search_data.get("results") or []
    lines: List[str] = []
    for item in results[:limit]:
        title = clean_text(item.get("title", ""))
        url = clean_text(item.get("url", ""))
        snippet = clean_text(item.get("snippet", ""))
        combined = f"{title} {snippet}"
        combined_lower = combined.lower()
        hints: List[str] = []
        directed = re.search(r"\bDirected by ([^.]+)", snippet, flags=re.I)
        if directed:
            hints.append(f"Directed by: {directed.group(1).strip()}")
        with_cast = re.search(r"\bWith ([^.]+)", snippet, flags=re.I)
        if with_cast:
            hints.append(f"Cast/people mentioned: {with_cast.group(1).strip()}")
        by_author = re.search(r"\bby ([A-Z][A-Za-z0-9_ .,&'-]{2,80})", snippet)
        if by_author and "directed by" not in snippet.lower():
            hints.append(f"Author/creator hint: {by_author.group(1).strip()}")
        year = re.search(r"\b(?:18|19|20|21)\d{2}\b", combined)
        if year:
            hints.append(f"Year mentioned: {year.group(0)}")
        if "short" in combined_lower and "film" in combined_lower:
            hints.append("Type hint: short film")
        elif "film" in combined_lower or "movie" in combined_lower:
            hints.append("Type hint: film/movie")
        if "github" in domain_from_url(url) or "github" in combined_lower:
            hints.append("Source hint: GitHub repository/project page")
        if any(x in combined_lower for x in ["documentation", "docs", "api reference", "readthedocs"]):
            hints.append("Source hint: documentation/API reference")
        if any(x in combined_lower for x in ["pypi", "package", "pip install"]):
            hints.append("Source hint: package/install information")
        lines.append(
            f"Result: {title}\n"
            f"URL: {url}\n"
            f"Snippet: {snippet}\n"
            f"Extracted hints: {', '.join(hints) if hints else 'none'}\n"
        )
    return "\n".join(lines).strip()
def extract_search_structured_context(search_data: Dict[str, Any]) -> Dict[str, Any]:
    results = search_data.get("results") or []
    structured = {
        "best_title": "",
        "best_url": "",
        "director": "",
        "cast": "",
        "year": "",
        "type_hint": "",
        "docs_url": "",
        "repo_url": "",
        "package_url": "",
    }

    if not results:
        return structured

    top = results[0]
    structured["best_title"] = clean_text(top.get("title", ""))
    structured["best_url"] = clean_text(top.get("url", ""))

    for item in results:
        title = clean_text(item.get("title", ""))
        url = clean_text(item.get("url", ""))
        snippet = clean_text(item.get("snippet", ""))
        combined = f"{title} {snippet}"
        combined_lower = combined.lower()
        domain = domain_from_url(url)

        if not structured["director"]:
            directed = re.search(r"\bDirected by ([^.]+)", snippet, flags=re.I)
            if directed:
                structured["director"] = directed.group(1).strip()

        if not structured["cast"]:
            with_cast = re.search(r"\bWith ([^.]+)", snippet, flags=re.I)
            if with_cast:
                structured["cast"] = with_cast.group(1).strip()

        if not structured["year"]:
            year = re.search(r"\b(?:18|19|20|21)\d{2}\b", combined)
            if year:
                structured["year"] = year.group(0)

        if not structured["type_hint"]:
            if "short" in combined_lower and "film" in combined_lower:
                structured["type_hint"] = "short film"
            elif "film" in combined_lower or "movie" in combined_lower:
                structured["type_hint"] = "film/movie"

        if not structured["repo_url"] and "github.com" in domain and "/blob/" not in url and "/issues" not in url:
            structured["repo_url"] = url

        if not structured["docs_url"]:
            if (
                "docs" in combined_lower
                or "documentation" in combined_lower
                or "readthedocs" in domain
                or "github.io" in domain
            ):
                structured["docs_url"] = url

        if not structured["package_url"]:
            if "pypi.org" in domain or "package" in combined_lower or "pip install" in combined_lower:
                structured["package_url"] = url

    return structured




# ============================================================
# PATCH 16 HELPER — local identity detector
# ============================================================

def looks_like_local_identity_question(text: str) -> bool:
    lowered = clean_text(text).lower().strip(" ?!.")
    if not lowered:
        return False

    patterns = (
        "who are you",
        "what are you",
        "what is your name",
        "what's your name",
        "whats your name",
        "who am i talking to",
        "what is this agent",
        "what agent is this",
        "what version are you",
        "what version is this",
        "what is your role",
        "what do you do",
        "describe yourself",
        "tell me about yourself",
    )
    return lowered.startswith(patterns)
# ============================================================
# PATCH 13B OVERRIDES — package follow-up + search guard
# These override earlier helper definitions without relying on fragile replace_exact blocks.
# ============================================================

def looks_like_contextual_followup(text: str) -> bool:
    lowered = clean_text(text).lower()
    if not lowered:
        return False

    # Prompt/dataset blocks often contain words like "that", "it", or "they",
    # but they are not contextual follow-up requests.
    dataset_markers = (
        "instruction:",
        "input:",
        "output:",
        "keywords:",
        "genre:",
        "narrative:",
        "main theme:",
        "positive_prompt:",
        "negative_prompt:",
        "hashtags:",
        "visualtags:",
        "title:",
        "description:",
    )
    if any(marker in lowered for marker in dataset_markers):
        return False

    followup_starts = (
        "it ",
        "that ",
        "this ",
        "they ",
        "them ",
        "he ",
        "she ",
        "the page ",
        "the result ",
        "the source ",
        "the link ",
        "the film ",
        "the movie ",
        "the short ",
        "the repo ",
        "the repository ",
        "the docs ",
        "the documentation ",
        "the package ",
        "the pypi page ",
        "the install page ",
        "who directed",
        "who starred",
        "who stars",
        "what was the cast",
        "what is the cast",
        "where is the repo",
        "where is the repository",
        "where are the docs",
        "where is the documentation",
        "where is the package",
        "where is the pypi",
        "where is the pypi page",
        "where can i install",
        "how do i install it",
        "install it",
        "package page",
        "pypi page",
        "what did that say",
        "what did it say",
        "summarize that",
        "summarize it",
        "open that",
        "follow that",
    )

    return lowered.startswith(followup_starts)

def extract_search_structured_context(search_data: Dict[str, Any]) -> Dict[str, Any]:
    results = search_data.get("results") or []
    structured = {
        "best_title": "",
        "best_url": "",
        "director": "",
        "cast": "",
        "year": "",
        "type_hint": "",
        "docs_url": "",
        "repo_url": "",
        "package_url": "",
    }

    if not results:
        return structured

    top = results[0]
    structured["best_title"] = clean_text(top.get("title", ""))
    structured["best_url"] = clean_text(top.get("url", ""))

    for item in results:
        title = clean_text(item.get("title", ""))
        url = clean_text(item.get("url", ""))
        snippet = clean_text(item.get("snippet", ""))
        combined = f"{title} {snippet}"
        combined_lower = combined.lower()
        domain = domain_from_url(url)

        if not structured["director"]:
            directed = re.search(r"\bDirected by ([^.]+)", snippet, flags=re.I)
            if directed:
                structured["director"] = directed.group(1).strip()

        if not structured["cast"]:
            with_cast = re.search(r"\bWith ([^.]+)", snippet, flags=re.I)
            if with_cast:
                structured["cast"] = with_cast.group(1).strip()

        if not structured["year"]:
            year = re.search(r"\b(?:18|19|20|21)\d{2}\b", combined)
            if year:
                structured["year"] = year.group(0)

        if not structured["type_hint"]:
            if "short" in combined_lower and "film" in combined_lower:
                structured["type_hint"] = "short film"
            elif "film" in combined_lower or "movie" in combined_lower:
                structured["type_hint"] = "film/movie"

        if not structured["repo_url"] and "github.com" in domain and "/blob/" not in url and "/issues" not in url:
            structured["repo_url"] = url

        if not structured["docs_url"]:
            if (
                "docs" in combined_lower
                or "documentation" in combined_lower
                or "readthedocs" in domain
                or "github.io" in domain
            ):
                structured["docs_url"] = url

        # Prefer a real PyPI project URL over weaker package/install hints.
        if "pypi.org/project/" in url:
            structured["package_url"] = url
        elif not structured["package_url"]:
            if "pypi.org" in domain or "package" in combined_lower or "pip install" in combined_lower:
                structured["package_url"] = url

    return structured


# ============================================================
# PATCH 14 OVERRIDES — query sanitizer + profile-aware hints
# ============================================================

def normalize_search_query(raw_query: str, source_hint: str = "") -> str:
    query = clean_text(raw_query)
    source_hint = clean_text(source_hint).lower()
    if not query:
        return ""

    # Repair pasted command residue like:
    # "pie 2018search imdb for pie 2018" -> "pie 2018"
    embedded_patterns = [
        r"search\s+imdb\s+(?:for\s+)?",
        r"search\s+wikipedia\s+(?:for\s+)?",
        r"search\s+wiki\s+(?:for\s+)?",
        r"search\s+github\s+(?:for\s+)?",
        r"search\s+docs\s+(?:for\s+)?",
        r"search\s+web\s+(?:for\s+)?",
        r"search\s+",
    ]
    for pattern in embedded_patterns:
        matches = list(re.finditer(pattern, query, flags=re.I))
        if not matches:
            continue
        last = matches[-1]
        before = clean_text(query[: last.start()])
        after = clean_text(query[last.end() :])
        if after:
            query = after
        elif before:
            query = before
        break

    # If the same phrase appears twice, keep one copy.
    words = query.split()
    if len(words) % 2 == 0 and words:
        half = len(words) // 2
        if words[:half] == words[half:]:
            query = " ".join(words[:half])

    query = clean_text(query)

    def ensure_suffix(q: str, suffix: str) -> str:
        tokens = q.lower().split()
        if suffix.lower() in tokens:
            return q
        return clean_text(f"{q} {suffix}")

    qlower = query.lower()
    if source_hint == "imdb":
        query = ensure_suffix(query, "imdb")
    elif source_hint == "wikipedia":
        query = ensure_suffix(query, "wikipedia")
    elif source_hint == "github":
        query = ensure_suffix(query, "github")
    elif source_hint == "docs":
        if "docs" not in qlower and "documentation" not in qlower:
            query = clean_text(f"{query} docs documentation")

    # Collapse accidental duplicate source terms.
    query = re.sub(r"\b(imdb)(?:\s+\1)+\b", r"\1", query, flags=re.I)
    query = re.sub(r"\b(github)(?:\s+\1)+\b", r"\1", query, flags=re.I)
    query = re.sub(r"\b(wikipedia)(?:\s+\1)+\b", r"\1", query, flags=re.I)
    query = re.sub(r"\b(docs)(?:\s+\1)+\b", r"\1", query, flags=re.I)

    return clean_text(query)


def extract_search_fact_hints(
    search_data: Dict[str, Any],
    *,
    limit: int = 3,
    answer_profile: str = "",
    source_hint: str = "",
) -> str:
    results = search_data.get("results") or []
    lines: List[str] = []
    profile = clean_text(answer_profile).lower()
    source = clean_text(source_hint).lower()
    film_mode = profile == "film_lookup" or source == "imdb"

    for item in results[:limit]:
        title = clean_text(item.get("title", ""))
        url = clean_text(item.get("url", ""))
        snippet = clean_text(item.get("snippet", ""))
        combined = f"{title} {snippet}"
        combined_lower = combined.lower()
        domain = domain_from_url(url)
        hints: List[str] = []

        if film_mode:
            directed = re.search(r"\bDirected by ([^.]+)", snippet, flags=re.I)
            if directed:
                hints.append(f"Directed by: {directed.group(1).strip()}")
            with_cast = re.search(r"\bWith ([^.]+)", snippet, flags=re.I)
            if with_cast:
                hints.append(f"Cast/people mentioned: {with_cast.group(1).strip()}")
            if "short" in combined_lower and "film" in combined_lower:
                hints.append("Type hint: short film")
            elif "film" in combined_lower or "movie" in combined_lower:
                hints.append("Type hint: film/movie")

        year = re.search(r"\b(?:18|19|20|21)\d{2}\b", combined)
        if year:
            hints.append(f"Year mentioned: {year.group(0)}")
        if "github" in domain or "github" in combined_lower:
            hints.append("Source hint: GitHub repository/project page")
        if any(x in combined_lower for x in ["documentation", "docs", "api reference", "readthedocs"]):
            hints.append("Source hint: documentation/API reference")
        if any(x in combined_lower for x in ["pypi", "package", "pip install"]):
            hints.append("Source hint: package/install information")

        lines.append(
            f"Result: {title}\n"
            f"URL: {url}\n"
            f"Snippet: {snippet}\n"
            f"Extracted hints: {', '.join(hints) if hints else 'none'}\n"
        )

    return "\n".join(lines).strip()


# ============================================================
# PATCH 18 HELPERS — temporary summon persona overlay
# ============================================================

def infer_summon_name(prompt: str) -> str:
    text = clean_text(prompt)
    if not text:
        return "Summoned Persona"
    match = re.search(r"\byou are ([A-Z][A-Za-z0-9_ .'-]{1,80})(?:,|\.|$)", text, flags=re.I)
    if match:
        return clean_text(match.group(1))
    return "Summoned Persona"


def parse_summon_payload(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    data = extract_first_json_object(raw)

    default_safety = [
        "Do not override grounding requirements.",
        "Do not invent factual claims when answering factual questions.",
    ]

    if isinstance(data, dict):
        persona_prompt = clean_text(data.get("persona_prompt") or data.get("prompt") or data.get("persona") or "")
        name = clean_text(data.get("name") or infer_summon_name(persona_prompt) or "Summoned Persona")
        identity_override = data.get("identity_override") if isinstance(data.get("identity_override"), dict) else {}
        if name and not identity_override.get("agent_name"):
            identity_override = dict(identity_override)
            identity_override["agent_name"] = name
        return {
            "active": True,
            "name": name,
            "mode": clean_text(data.get("mode") or "roleplay"),
            "persona_prompt": persona_prompt or raw,
            "tone": clean_text(data.get("tone") or ""),
            "style_rules": data.get("style_rules") if isinstance(data.get("style_rules"), list) else [],
            "world_rules": data.get("world_rules") if isinstance(data.get("world_rules"), list) else [],
            "format_rules": data.get("format_rules") if isinstance(data.get("format_rules"), list) else [],
            "safety_rules": data.get("safety_rules") if isinstance(data.get("safety_rules"), list) else default_safety,
            "identity_override": identity_override,
            "prompt_slots": data.get("prompt_slots") if isinstance(data.get("prompt_slots"), dict) else {},
            "metadata": data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
            "created_at": now_str(),
        }

    raw = raw.strip("\"'")
    name = infer_summon_name(raw)
    return {
        "active": True,
        "name": name,
        "mode": "roleplay",
        "persona_prompt": raw,
        "tone": "",
        "style_rules": [],
        "world_rules": [],
        "format_rules": [],
        "safety_rules": default_safety,
        "identity_override": {
            "agent_name": name,
            "agent_role": "summoned roleplay persona",
            "profile": "temporary summon overlay",
            "description": raw,
        },
        "prompt_slots": {},
        "metadata": {},
        "created_at": now_str(),
    }


# ============================================================
# PATCH 19 HELPER — summon embodiment routing detector
# ============================================================

def looks_like_summon_embodiment_question(text: str) -> bool:
    lowered = clean_text(text).lower().strip(" ?!.")
    if not lowered:
        return False

    patterns = (
        "what do you do",
        "what is your life like",
        "what's your life like",
        "whats your life like",
        "where are you",
        "what world are you from",
        "tell me about yourself",
        "describe yourself",
        "what are you working on",
        "what is happening",
        "what's happening",
        "whats happening",
        "what do you see",
        "where do you live",
        "what is this place",
    )
    return lowered.startswith(patterns)


# ============================================================
# PATCH 21 HELPER — summon chat priority detector
# ============================================================

def looks_like_summon_chat_request(text: str) -> bool:
    lowered = clean_text(text).lower().strip(" ?!.")
    if not lowered:
        return False

    starts = (
        "explain ",
        "describe ",
        "tell me about ",
        "as ",
        "in character",
        "roleplay ",
        "continue ",
        "what is ",
        "what are ",
        "how does ",
        "how do ",
        "why does ",
        "why do ",
        "give me ",
        "show me ",
        "write ",
        "say ",
    )
    return lowered.startswith(starts)


# ============================================================
# PATCH 21 OVERRIDE — search query sanitizer cleanup
# ============================================================

def _normalize_docs_release_query(query: str, source_hint: str = "") -> str:
    """Normalize official-docs/release-note searches without losing the subject.

    This specifically avoids turning prompts like
    "find official docs and release notes for Python 3.14, cite sources" into
    "and release notes for Python 3.14 ...". It strips answer instructions
    such as citation requests, then rebuilds a compact query around the subject.
    """
    raw = clean_text(query)
    if not raw:
        return ""

    cleaned = re.sub(
        r"(?:,?\s*\b(?:please\s+)?(?:cite|include|provide)\s+(?:your\s+)?(?:sources|citations|references)\b)",
        "",
        raw,
        flags=re.I,
    )
    cleaned = re.sub(r"\bwith\s+(?:citations|sources|references)\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\busing\s+(?:citations|sources|references)\b", "", cleaned, flags=re.I)
    cleaned = clean_text(cleaned).strip(" ,.;:")

    lowered = cleaned.lower()
    has_docs = bool(re.search(r"\b(?:official\s+)?(?:docs|documentation|manual|api\s+reference)\b", lowered)) or source_hint == "docs"
    has_release = bool(re.search(r"\brelease\s+notes?\b", lowered))
    if not (has_docs or has_release):
        return cleaned

    subject = ""
    # Match "official docs and release notes for Python 3.14" and also the
    # damaged intermediate form "and release notes for Python 3.14".
    patterns = (
        r"(?:^|\b)(?:find|get|show|look\s+up|search\s+for|search|official\s+docs|official\s+documentation|docs|documentation|manual|api\s+reference|and\s+release\s+notes?|release\s+notes?)"
        r"(?:\s+and\s+(?:official\s+docs|official\s+documentation|docs|documentation|release\s+notes?))*"
        r"\s+(?:for|about|on)\s+(?P<subject>.+)$",
        r"(?:for|about|on)\s+(?P<subject>.+?)\s+(?:official\s+docs|official\s+documentation|docs|documentation|release\s+notes?)\b",
    )
    for pattern in patterns:
        m = re.search(pattern, cleaned, flags=re.I)
        if m:
            subject = clean_text(m.group("subject")).strip(" ,.;:")
            break

    if subject:
        # Remove any leftover answer instructions that appeared after the subject.
        subject = re.sub(r"\b(?:cite|include|provide)\s+(?:sources|citations|references)\b.*$", "", subject, flags=re.I).strip(" ,.;:")
        subject = re.sub(r"\bwith\s+(?:sources|citations|references)\b.*$", "", subject, flags=re.I).strip(" ,.;:")
        parts = [subject]
        if has_docs:
            parts.append("official documentation")
        if has_release:
            parts.append("release notes")
        return clean_text(" ".join(parts))

    # No clear subject, but still remove citation instructions cleanly.
    return cleaned


def normalize_search_query(raw_query: str, source_hint: str = "") -> str:
    query = clean_text(raw_query)
    source_hint = clean_text(source_hint).lower()
    if not query:
        return ""

    query = _normalize_docs_release_query(query, source_hint)

    # Keep response-shape requests out of the search query.
    format_patterns = [
        r"\b(?:in|as)\s+a\s+numbered\s+list\b",
        r"\b(?:as|in)\s+numbered\s+list\b",
        r"\bnumbered\s+list\b",
        r"\b(?:in|as)\s+bullet\s+points\b",
        r"\b(?:as|in)\s+bullets\b",
        r"\bbriefly\b",
        r"\bstep\s+by\s+step\b",
        r"\bwith\s+sources\b",
        r"\bwith\s+links\b",
    ]
    for pattern in format_patterns:
        query = re.sub(pattern, "", query, flags=re.I).strip()
    query = re.sub(
        r"^\s*(?:create|make|give\s+me|show\s+me)?\s*(?:a\s+)?list\s+of\s+",
        "",
        query,
        flags=re.I,
    ).strip()

    # Repair pasted command residue like:
    # "pie 2018search imdb for pie 2018" -> "pie 2018"
    embedded_patterns = [
        r"search\s+(?:the\s+)?internet\s+(?:for\s+)?",
        r"search\s+imdb\s+(?:for\s+)?",
        r"search\s+wikipedia\s+(?:for\s+)?",
        r"search\s+wiki\s+(?:for\s+)?",
        r"search\s+github\s+(?:for\s+)?",
        r"search\s+docs\s+(?:for\s+)?",
        r"search\s+web\s+(?:for\s+)?",
        r"search\s+",
    ]
    for pattern in embedded_patterns:
        matches = list(re.finditer(pattern, query, flags=re.I))
        if not matches:
            continue
        last = matches[-1]
        before = clean_text(query[: last.start()])
        after = clean_text(query[last.end() :])
        if after:
            query = after
        elif before:
            query = before
        break

    # Strip leftover natural-language source phrases.
    query = re.sub(r"^(?:the\s+)?internet\s+(?:for\s+)?", "", query, flags=re.I).strip()
    query = re.sub(r"^(?:the\s+)?web\s+(?:for\s+)?", "", query, flags=re.I).strip()
    query = re.sub(r"^(?:online\s+)?(?:for\s+)?", "", query, flags=re.I).strip()
    query = re.sub(r"\b(?:on|from|at|in)\s+(?:git\s*hub|github)\b", "", query, flags=re.I).strip()

    # If the same phrase appears twice, keep one copy.
    words = query.split()
    if len(words) % 2 == 0 and words:
        half = len(words) // 2
        if words[:half] == words[half:]:
            query = " ".join(words[:half])

    query = clean_text(query)

    def ensure_suffix(q: str, suffix: str) -> str:
        tokens = q.lower().split()
        if suffix.lower() in tokens:
            return q
        return clean_text(f"{q} {suffix}")

    qlower = query.lower()
    if source_hint == "imdb":
        query = ensure_suffix(query, "imdb")
    elif source_hint == "wikipedia":
        query = ensure_suffix(query, "wikipedia")
    elif source_hint == "github":
        if "site:github.com" not in qlower and "github.com" not in qlower:
            query = clean_text(f"{query} site:github.com")
    elif source_hint == "docs":
        if "docs" not in qlower and "documentation" not in qlower:
            query = clean_text(f"{query} docs documentation")

    # Collapse accidental duplicate source terms.
    query = re.sub(r"\b(imdb)(?:\s+\1)+\b", r"\1", query, flags=re.I)
    query = re.sub(r"\b(github)(?:\s+\1)+\b", r"\1", query, flags=re.I)
    query = re.sub(r"\b(wikipedia)(?:\s+\1)+\b", r"\1", query, flags=re.I)
    query = re.sub(r"\b(docs)(?:\s+\1)+\b", r"\1", query, flags=re.I)

    return clean_text(query)

# ============================================================

# ============================================================
# DATASET/PROMPT BLOCK ROUTING HELPER
# ============================================================

def looks_like_dataset_prompt_block(text: str) -> bool:
    lowered = clean_text(text).lower()
    if not lowered:
        return False

    dataset_markers = (
        "instruction:",
        "input:",
        "output:",
        "keywords:",
        "positive_prompt:",
        "negative_prompt:",
        "hashtags:",
        "visualtags:",
        "genre:",
        "narrative:",
        "main theme:",
    )

    marker_count = sum(1 for marker in dataset_markers if marker in lowered)

    # Require output: so ordinary prompts with words like input/genre are not trapped.
    return "output:" in lowered and marker_count >= 2

