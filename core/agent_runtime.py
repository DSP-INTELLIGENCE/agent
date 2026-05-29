#!/usr/bin/env python3
from __future__ import annotations

"""
agent.py

Stable local intelligent agent core.

Core features:
- local chat via Ollama
- slash commands map directly to terminal commands
- router -> planner -> dispatcher architecture
- planner-side validation and readable validation errors
- Wikipedia-first grounded answers
- multi-source web fallback with source confidence gate
- web search/fetch/link extraction/follow/summarize flow
- local memory and session save/load
- streaming output through event emissions
- copy-friendly plain terminal mode
- optional pyTermTk TUI mode
- no image generation
- no Stable Diffusion / A1111

Install:
    pip install requests
    pip install pyTermTk requests   # only needed for TUI mode

Run:
    python agent.py --plain
    python agent.py
"""

import html
import ipaddress
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import requests

from core.constants import *
from core.defaults import *
from core.helpers import *
from core.terminal_input import *
from core.events import *
from core.types import *
from core.grounding_source_guard import (
    evaluate_grounding_request,
    grounding_supports_answer,
)

from core.patch_frontdoor import (
    PatchFrontdoorError,
    patch_help_text,
    run_patch_command,
)
ttk = None

PROMPT_LANE_ROOTS: Tuple[str, ...] = (
    "/prompt",
)


LEGACY_UNWIRED_SLASH_COMMANDS: Tuple[str, ...] = (
    '/question',
    '/write',
    '/generate',
    '/discuss',
    '/explain',
    '/describe',
    '/summarize',
    '/analyze',
    '/list',
    '/story',
    '/rag',
    '/research',
    '/route',
    '/plan',
    '/agent',
    '/agentspec',
    '/agent-spec',
    '/agentscript',
    '/agent-script',
    '/semantic',
    '/semantic-route',
    '/semantic_router',
    '/encoder',
    '/encode',
)


def require_ttk() -> Any:
    """Lazy-load pyTermTk only for TUI mode."""
    global ttk
    if ttk is not None:
        return ttk
    try:
        import TermTk as _ttk
    except Exception as exc:
        raise SystemExit(
            "pyTermTk is required for TUI mode. Install it with: pip install pyTermTk\n"
            "Or run copyable console mode with: python agent.py --plain\n"
            f"Import error: {exc}"
        )
    ttk = _ttk
    return ttk


# ============================================================

# Phase 1-4 refactor: constants/defaults live in core.constants and core.defaults.


# Phase 1-4 refactor: helpers/input utilities live in core.helpers and core.terminal_input.



# Prompt-leak cleanup
# ============================================================

INTERNAL_PROMPT_MARKERS: Tuple[str, ...] = (
    "ANSWERING RULE",
    "ANSWERING RULE:",
    "TOOL EVIDENCE",
    "USER TASK",
    "USER ORIGINAL REQUEST",
    "SEARCH QUERY USED",
    "SOURCE HINT",
    "ANSWER PROFILE",
    "RESPONSE FORMAT HINT",
    "SPECIFIC INSTRUCTION",
    "GROUNDING POLICY",
    "GROUNDING QUERY PLAN",
    "MULTI-SOURCE GROUNDING",
    "WIKIPEDIA GROUNDING",
    "WEB SEARCH FALLBACK",
)



def clean_internal_prompt_leak(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return raw
    if not any(marker.lower() in raw.lower() for marker in INTERNAL_PROMPT_MARKERS):
        return raw

    answer_match = re.search(r"(?:^|\n)\s*answer\s*:\s*(.+)\s*$", raw, flags=re.I | re.S)
    if answer_match:
        candidate = answer_match.group(1).strip()
        if candidate:
            return candidate

    cleaned_lines: List[str] = []
    skip_block = False
    label_re = re.compile(
        r"^\s*(?:ANSWERING RULE|TOOL EVIDENCE|USER TASK|USER ORIGINAL REQUEST|SEARCH QUERY USED|"
        r"SOURCE HINT|ANSWER PROFILE|RESPONSE FORMAT HINT|SPECIFIC INSTRUCTION|GROUNDING POLICY|"
        r"GROUNDING QUERY PLAN|MULTI-SOURCE GROUNDING|WIKIPEDIA GROUNDING|WEB SEARCH FALLBACK)\s*:?\s*$",
        re.I,
    )
    for line in raw.splitlines():
        stripped = line.strip()
        if label_re.match(stripped):
            skip_block = True
            continue
        if skip_block and not stripped:
            skip_block = False
            continue
        if skip_block:
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines).strip()
    return cleaned or raw


# LOCAL TOOL HELPERS
# ============================================================

TOOL_READ_MAX_BYTES = 65536
TOOL_RUN_TIMEOUT_SECONDS = 10
TOOL_SHELL_ALLOWED_COMMANDS = {"pwd", "ls", "find", "cat", "head", "tail", "wc", "grep"}
TOOL_SHELL_CHAIN_SEPARATORS = {"&&", ";"}
TOOL_SHELL_BLOCKED_TOKENS = {"rm", "rmdir", "mv", "cp", "chmod", "chown", "sudo", "su", "dd", "mkfs", "mount", "umount", "curl", "wget", "ssh", "scp", "ftp", "nc", "netcat", "kill", "pkill", "reboot", "shutdown"}
TOOL_SHELL_BLOCKED_CHARS = set("|><`$(){}")
TEXT_FILE_SUFFIX_ALLOWLIST = {"", ".txt", ".md", ".py", ".sh", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".csv", ".log", ".rst", ".html", ".css", ".js", ".ts", ".cpp", ".c", ".h", ".hpp"}


def tool_root() -> Path:
    return Path.cwd().resolve()


def resolve_safe_tool_path(path_text: str = ".") -> Path:
    root = tool_root()
    raw = clean_text(path_text or ".")
    raw = raw.strip() or "."
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise RuntimeError(f"Path is outside the agent working directory: {raw}")
    return resolved


def format_tool_completed_process(args: List[str], proc: subprocess.CompletedProcess[str]) -> str:
    cmdline = " ".join(shlex.quote(x) for x in args)
    parts = [f"$ {cmdline}", f"exit_code: {proc.returncode}"]
    stdout = (proc.stdout or "").rstrip()
    stderr = (proc.stderr or "").rstrip()
    if stdout:
        parts.extend(["", "stdout:", truncate_text(stdout, 12000)])
    if stderr:
        parts.extend(["", "stderr:", truncate_text(stderr, 4000)])
    return "\n".join(parts).rstrip()


def split_shell_segments(command: str) -> List[List[str]]:
    raw = str(command or "").strip()
    if not raw:
        raise RuntimeError("shell.run requires a command.")
    if any(ch in raw for ch in TOOL_SHELL_BLOCKED_CHARS):
        raise RuntimeError("shell.run blocked metacharacters. Allowed chaining is limited to && and ;.")
    tokens = shlex.split(raw)
    if not tokens:
        raise RuntimeError("shell.run requires a command.")
    segments: List[List[str]] = []
    current: List[str] = []
    for token in tokens:
        if token in TOOL_SHELL_CHAIN_SEPARATORS:
            if current:
                segments.append(current)
                current = []
            continue
        current.append(token)
    if current:
        segments.append(current)
    if not segments:
        raise RuntimeError("shell.run requires a command.")
    return segments


def validate_shell_segments(segments: List[List[str]]) -> None:
    if len(segments) > 4:
        raise RuntimeError("shell.run allows at most 4 chained read-only commands.")
    root = tool_root()
    for seg in segments:
        executable = Path(seg[0]).name
        if executable in TOOL_SHELL_BLOCKED_TOKENS:
            raise RuntimeError(f"shell.run blocked unsafe command: {executable}")
        if executable not in TOOL_SHELL_ALLOWED_COMMANDS:
            allowed = ", ".join(sorted(TOOL_SHELL_ALLOWED_COMMANDS))
            raise RuntimeError(f"shell.run only allows read-only commands: {allowed}")
        for arg in seg[1:]:
            if not arg or arg.startswith("-"):
                continue
            # Keep shell.run project-local. Patterns are allowed, but explicit absolute
            # paths or parent traversal are rejected.
            if arg.startswith("/") or ".." in Path(arg).parts:
                raise RuntimeError(f"shell.run only allows project-relative paths: {arg}")
            if any(sep in arg for sep in ("/", os.sep)) and not any(ch in arg for ch in "*?[]"):
                try:
                    resolve_safe_tool_path(arg)
                except RuntimeError as exc:
                    raise RuntimeError(str(exc)) from exc


def extract_shell_command_from_text(text: str) -> str:
    raw = clean_text(text)
    patterns = [
        r"^run\s+(?:the\s+)?shell\s+command\s+",
        r"^run\s+(?:the\s+)?command\s+",
        r"^shell\s+",
        r"^bash\s+",
    ]
    for pattern in patterns:
        raw = re.sub(pattern, "", raw, flags=re.I).strip()
    raw = re.sub(r"\s+and\s+then\s+", " && ", raw, flags=re.I)
    return raw


def extract_fs_read_path(text: str) -> str:
    raw = clean_text(text)
    raw = re.sub(r"^(?:read|open|show|print|display)\s+(?:the\s+)?(?:file\s+)?", "", raw, flags=re.I).strip()
    return raw


def extract_python_code_from_text(text: str) -> str:
    raw = str(text or "").strip()
    fence = re.search(r"```(?:python|py)?\s*(.*?)```", raw, flags=re.I | re.S)
    if fence:
        return fence.group(1).strip()
    for pattern in (
        r"^/python\s+",
        r"^/py\s+",
        r"^run\s+(?:this\s+)?python\s+(?:code|script)\s*:?\s*",
        r"^run\s+python\s+(?:code|script)?\s*(?:that\s+|to\s+)?",
        r"^write\s+and\s+run\s+(?:a\s+)?(?:short\s+)?python\s+(?:code|script)?\s*(?:that\s+)?",
    ):
        raw = re.sub(pattern, "", raw, flags=re.I | re.S).strip()

    # Deterministic natural-language snippets for common safe smoke tests.
    m = re.search(r"first\s+(\d+)\s+fibonacci", raw, flags=re.I)
    if m:
        n = max(1, min(int(m.group(1)), 100))
        return "a, b = 0, 1\nfor _ in range(%d):\n    print(a)\n    a, b = b, a + b" % n

    m = re.search(r"first\s+(\d+)\s+square\s+numbers?", raw, flags=re.I)
    if m:
        n = max(1, min(int(m.group(1)), 100))
        return "for i in range(1, %d):\n    print(i * i)" % (n + 1)

    # Convert simple prose like "prints hello" or "to print \"agent ok\""
    # into valid Python instead of passing pseudo-code through to the runner.
    m = re.match(r"^(?:to\s+)?prints?\s+(?:the\s+word\s+)?(?P<value>.+?)\.?$", raw, flags=re.I | re.S)
    if m:
        value = m.group("value").strip().strip("'\"")
        if value and not re.search(r"\b(?:script|code|program|range|loop)\b", value, flags=re.I):
            return f"print({value!r})"

    return raw


# GROUNDING HELPERS
# ============================================================

def is_agent_router_explain_request(text: str) -> bool:
    raw = clean_text(text).lower()
    if not raw:
        return False
    has_router = "router" in raw or "routing" in raw
    has_agent_context = any(
        phrase in raw
        for phrase in (
            "this agent",
            "the agent",
            "agent router",
            "agent routing",
            "in agent",
            "in this project",
        )
    )
    has_explain = any(word in raw for word in ("explain", "what", "describe", "how"))
    return has_router and has_agent_context and has_explain


def format_agent_router_explanation() -> str:
    return (
        "In this agent, the router is the deterministic layer that decides what to do "
        "with each user request before any normal chat reply. It handles exact slash "
        "commands such as /guard, /config, /plan, and /tool first; then it routes "
        "safe local actions to the manifest-driven /tool bridge, file listing, shell, "
        "Python, grounding, memory, or normal chat paths. /paste is only multiline "
        "input collection, and after /endpaste the collected text routes exactly like "
        "normal input. The router also keeps safety boundaries in place: tools run "
        "through manifests and argument allowlists, risky shell actions are gated, "
        "and grounded/web lookup only happens when the request is routed there."
    )


def looks_like_open_ended_chat_prompt(text: str) -> bool:
    """Route open-ended advice/idea prompts to chat, not factual grounding."""
    raw = clean_text(text)
    lowered = raw.lower()
    if not raw:
        return False

    # Explicit research/search/current-facts requests should still be allowed
    # to reach web/grounding routes.
    if re.search(r"\b(?:search|browse|look\s+up|find\s+online|web\s+search|latest|today|current\s+news|news|sources?|cite|citation)\b", lowered):
        return False

    idea_patterns = [
        r"^what\s+are\s+some\b.+\b(?:ideas?|suggestions?|ways?|tips?|options?)\b",
        r"^give\s+me\s+(?:some\s+)?(?:ideas?|suggestions?|ways?|tips?|options?)\b",
        r"^suggest\s+(?:some\s+)?",
        r"^brainstorm\s+",
        r"^help\s+me\s+(?:come\s+up\s+with|think\s+of|plan)\b",
        r"^what\s+should\s+i\b",
    ]
    return any(re.search(pattern, lowered, flags=re.I) for pattern in idea_patterns)


def infer_grounding_profile(query: str) -> str:
    lowered = clean_text(query).lower()
    film_markers = [
        "imdb", "movie", "film", "short film", "director", "directed by",
        "cast", "actor", "actress", "release date", "letterboxd", "tmdb",
    ]
    if any(marker in lowered for marker in film_markers):
        return "film"

    software_markers = [
        "python", "javascript", "api", "library", "package", "github",
        "docs", "documentation", "function", "class", "module", "pip",
        "pytermtk", "ollama", "requests", "c++", "polyblep", "blep",
        "dsp", "synthesis",
    ]
    if any(marker in lowered for marker in software_markers):
        return "software"

    return "general_reference"


def strip_question_boilerplate(text: str) -> str:
    raw = clean_text(text).strip(" ?!.,;:\n\t")
    song_author_match = re.match(r"^who\s+wrote\s+(?:the\s+)?song\s+(.+)$", raw, flags=re.IGNORECASE)
    if song_author_match:
        song = clean_text(song_author_match.group(1)).strip(" ?!.,;:")
        if song:
            return clean_text(f"{song} song")

    patterns = [
        r"^(?:please\s+)?explain\s+",
        r"^(?:please\s+)?define\s+",
        r"^who\s+directed\s+",
        r"^who\s+is\s+",
        r"^who\s+was\s+",
        r"^what\s+is\s+",
        r"^what\s+are\s+",
        r"^when\s+was\s+",
        r"^when\s+did\s+",
        r"^where\s+is\s+",
        r"^where\s+was\s+",
        r"^is\s+there\s+",
        r"^does\s+",
        r"^did\s+",
        r"^was\s+",
        r"^were\s+",
        r"^tell\s+me\s+about\s+",
        r"^search\s+(?:the\s+)?web\s+for\s+",
        r"^search\s+imdb\s+for\s+",
        r"^search\s+wikipedia\s+for\s+",
        r"^search\s+wiki\s+for\s+",
        r"^look\s+up\s+",
    ]
    cleaned = raw
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(
        r"\b(directed|director|cast|release date|released|movie|film|short film)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    cleaned = re.sub(r"^(?:the|a|an)\s+", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ?!.,;:")
    return cleaned or raw


def extract_years(text: str) -> List[str]:
    return re.findall(r"\b(?:18|19|20|21)\d{2}\b", str(text or ""))


def extract_required_terms(text: str, *, max_terms: int = 8) -> List[str]:
    stopwords = {
        "what", "when", "where", "which", "who", "why", "how", "the", "a", "an",
        "is", "are", "was", "were", "be", "been", "and", "or", "not", "true", "false",
        "for", "from", "that", "this", "with", "about", "directed", "director",
        "movie", "film", "short", "search", "web", "define", "explain", "tell", "me",
    }
    terms: List[str] = []
    seen = set()
    for token in tokenize(text):
        t = token.lower().strip("._-/:")
        if not t or t in stopwords:
            continue
        if t in seen:
            continue
        seen.add(t)
        terms.append(t)
        if len(terms) >= max_terms:
            break
    return terms


def dedupe_result_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for item in items:
        url = clean_text(item.get("url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(item)
    return out


def source_result_context(results: List[Dict[str, Any]], limit: int = 10) -> str:
    lines: List[str] = []
    for item in results[:limit]:
        lines.append(
            f"{item.get('index', '')}. {item.get('title', '')}\n"
            f"URL: {item.get('url', '')}\n"
            f"Snippet: {item.get('snippet', '')}\n"
        )
    return "\n".join(lines)


# ============================================================

# Phase 1-4 refactor: events live in core.events.


# Phase 1-4 refactor: shared dataclasses live in core.types.

def build_grounding_query(user_text: str) -> GroundingQuery:
    original = clean_text(user_text)
    profile = infer_grounding_profile(original)
    base = strip_question_boilerplate(original) or original
    birth_match = re.search(r"^\s*(?:was|is)\s+(.+?)\s+born\b", original, flags=re.I)
    if birth_match:
        person = clean_text(birth_match.group(1)).strip(" ?!.,;:")
        if person:
            base = clean_text(f"{person} birth date birthplace")
    years = extract_years(original)
    for year in years:
        if year not in base:
            base = clean_text(f"{base} {year}")

    wikipedia_query = base
    web_query = base
    optional_terms: List[str] = []
    preferred_domains = list(GROUNDING_SOURCE_PROFILES.get(profile, []))

    lowered = original.lower()
    if profile == "film":
        optional_terms = ["director", "directed", "film", "short", "cast", "movie"]
        if any(word in lowered for word in ["director", "directed", "who directed"]):
            web_query = clean_text(f"{base} director IMDb TMDB Letterboxd")
        elif "cast" in lowered:
            web_query = clean_text(f"{base} cast IMDb TMDB Letterboxd")
        else:
            web_query = clean_text(f"{base} IMDb TMDB Letterboxd")
    elif profile == "software":
        if any(term in lowered for term in ["polyblep", "blep", "oscillator", "audio", "dsp", "synthesis"]):
            optional_terms = ["audio", "dsp", "synthesis", "c++", "github", "documentation", "tutorial"]
            preferred_domains = ["github.com", "martin-finke.de", "dsprelated.com", "earlevel.com"]
            web_query = clean_text(f"{base} audio DSP C++ GitHub documentation tutorial")
        else:
            optional_terms = ["python", "tui", "terminal", "github", "documentation", "docs", "package", "library"]
            web_query = clean_text(f"{base} Python TUI library GitHub documentation")
    else:
        optional_terms = ["wikipedia", "britannica", "reference", "history", "official"]
        web_query = base

    required_terms = extract_required_terms(base) or extract_required_terms(original)
    return GroundingQuery(
        original=original,
        profile=profile,
        wikipedia_query=wikipedia_query,
        web_query=web_query,
        required_terms=required_terms,
        optional_terms=optional_terms,
        preferred_domains=preferred_domains,
    )


GENERIC_GROUNDING_TERMS = {
    "oscillator", "equation", "problem", "system", "method", "guide",
    "tutorial", "article", "news", "story", "current", "today", "latest",
    "reference", "history", "official", "docs", "documentation", "library",
    "package", "function", "class", "module", "software", "python", "audio",
}


def important_required_terms(grounding_query: GroundingQuery) -> List[str]:
    important: List[str] = []
    for term in grounding_query.required_terms or []:
        t = clean_text(term).lower().strip("._-/:#")
        if not t or len(t) < 5:
            continue
        if t in GENERIC_GROUNDING_TERMS:
            continue
        if t not in important:
            important.append(t)
    return important


def _entity_title_tokens(text: str) -> List[str]:
    normalized = clean_text(text).lower()
    return [token for token in tokenize(normalized) if token and token not in GENERIC_GROUNDING_TERMS]


def title_matches_grounding_entity(title: str, grounding_query: GroundingQuery) -> Optional[bool]:
    """Return False for loose embedded title hits that should not ground an entity.

    A query like "cocoa puffs" must not be accepted just because a different
    title embeds that phrase, such as "Sex, Drugs, and Cocoa Puffs". For
    multi-term entity targets, require the title to start with the target's
    leading term and contain the rest of the target terms. Return None when the
    target is too broad for this gate.
    """
    target_tokens = _entity_title_tokens(grounding_query.wikipedia_query or grounding_query.original)
    if len(target_tokens) < 2:
        return None

    title_tokens = _entity_title_tokens(title)
    if not title_tokens:
        return False
    if title_tokens[0] != target_tokens[0]:
        return False
    return all(token in title_tokens for token in target_tokens)


def grounding_ambiguity_reason(original: str, grounding_query: GroundingQuery) -> str:
    raw = clean_text(original).strip(" ?!.,;:")
    base = clean_text(grounding_query.wikipedia_query or grounding_query.original).strip(" ?!.,;:")
    if re.match(r"^where\s+is\s+\S+\??$", raw, flags=re.IGNORECASE):
        base_tokens = tokenize(base)
        if len(base_tokens) == 1 and len(base_tokens[0]) <= 4:
            return f"The location query is ambiguous: '{base}'. Please specify what you mean before I ground an answer."
    return ""


def _strip_grounding_target_article(text: str) -> str:
    value = clean_text(text).strip(" ?!.,;:\n\t")
    value = re.sub(r"^(?:a|an|the)\s+", "", value, flags=re.IGNORECASE)
    return clean_text(value)


def grounding_conjunction_targets(original: str, grounding_query: GroundingQuery) -> List[str]:
    """Extract conservative multi-target reference queries.

    This is intentionally narrow. It handles prompts such as
    "what is pie and cake?" by returning ["pie", "cake"], while avoiding
    broad natural-language phrases and embedded titles like
    "Sex, Drugs, and Cocoa Puffs".
    """
    raw = clean_text(original).strip(" ?!.,;:\n\t")
    base = clean_text(grounding_query.wikipedia_query or grounding_query.original).strip(" ?!.,;:\n\t")
    if not raw or not base:
        return []

    raw_lower = raw.lower()
    if not re.match(
        r"^(?:please\s+)?(?:what\s+(?:is|are)|define|explain|describe|tell\s+me\s+about)\b",
        raw_lower,
    ):
        return []

    # Comma lists are too often titles or broad lists; keep v1 to simple A and B.
    if "," in base or ";" in base:
        return []

    if not re.search(r"\s+(?:and|or)\s+", base, flags=re.IGNORECASE):
        return []

    parts = [
        _strip_grounding_target_article(part)
        for part in re.split(r"\s+(?:and|or)\s+", base, flags=re.IGNORECASE)
    ]
    parts = [part for part in parts if part]
    if len(parts) < 2 or len(parts) > 4:
        return []

    blocked_tokens = {
        "who", "what", "when", "where", "why", "how", "is", "are", "was", "were",
        "wrote", "write", "made", "make", "did", "does", "do", "using", "sources",
    }
    targets: List[str] = []
    seen = set()
    for part in parts:
        tokens = tokenize(part)
        if not tokens or len(tokens) > 4:
            return []
        if any(token in blocked_tokens for token in tokens):
            return []
        normalized = clean_text(part).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        targets.append(clean_text(part))

    return targets if len(targets) >= 2 else []


def score_source_against_query(
    item: Dict[str, Any],
    grounding_query: GroundingQuery,
    page_text: str = "",
) -> SourceConfidence:
    url = clean_text(item.get("url") or "")
    title = clean_text(item.get("title") or "")
    snippet = clean_text(item.get("snippet") or "")
    domain = domain_from_url(url)
    combined = f"{title} {snippet} {clean_text(page_text)[:5000]}".lower()

    score = 0.0
    reasons: List[str] = []
    required_terms = [t.lower() for t in grounding_query.required_terms if t]
    optional_terms = [t.lower() for t in grounding_query.optional_terms if t]

    required_matches = 0
    important_terms = important_required_terms(grounding_query)
    important_matches = 0
    for term in required_terms:
        if term in combined:
            required_matches += 1
            if term in important_terms:
                important_matches += 1
                score += 3.0
                reasons.append(f"important required term matched: {term}")
            else:
                score += 1.25
                reasons.append(f"required term matched: {term}")

    for term in optional_terms:
        if term in combined:
            score += 0.5
            reasons.append(f"optional term matched: {term}")

    if any(preferred in domain for preferred in grounding_query.preferred_domains):
        score += 2.0
        reasons.append(f"preferred domain: {domain}")

    if source_priority_score(url) < len(TRUSTED_SOURCE_PRIORITY):
        score += 1.0
        reasons.append(f"trusted source priority: {domain}")

    title_entity_match = title_matches_grounding_entity(title, grounding_query)
    if title_entity_match is False:
        score -= 5.0
        reasons.append("title does not match target entity")
    elif title_entity_match is True:
        score += 1.5
        reasons.append("title matches target entity")

    if not required_matches and required_terms:
        score -= 3.0
        reasons.append("no required terms matched")

    if len(clean_text(snippet + " " + page_text)) < 80:
        score -= 1.0
        reasons.append("thin source text")

    important_gate = important_matches > 0 or not important_terms
    if important_terms and not important_matches:
        score -= 4.0
        reasons.append("no important required terms matched")
    required_gate = required_matches > 0 or not required_terms
    entity_gate = title_entity_match is not False
    accepted = entity_gate and important_gate and required_gate and (score >= (2.0 if len(required_terms) <= 1 else 2.5))
    return SourceConfidence(url=url, title=title, score=round(score, 3), accepted=bool(accepted), reasons=reasons)


def filter_candidates_by_confidence(
    items: List[Dict[str, Any]],
    grounding_query: GroundingQuery,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    accepted: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    for item in items:
        confidence = score_source_against_query(item, grounding_query)
        enriched = dict(item)
        enriched["source_confidence"] = confidence.to_dict()
        if confidence.accepted:
            accepted.append(enriched)
        else:
            rejected.append(enriched)
    accepted.sort(key=lambda it: float(it.get("source_confidence", {}).get("score", 0.0)), reverse=True)
    rejected.sort(key=lambda it: float(it.get("source_confidence", {}).get("score", 0.0)), reverse=True)
    return accepted, rejected




# ============================================================
# PLUGIN CONTRACT / LOADER
# Phase 5 step 1-4 refactor: plugin dataclass, validation, result normalization,
# and natural-language trigger helpers live in core.plugins.
# ============================================================

from core.plugins import (
    PluginManager,
    PluginRecord,
    _as_string_list,
    match_plugin_natural_language_trigger,
    normalize_plugin_result,
    safe_plugin_id_to_dirname,
    validate_plugin_manifest,
)
from core.cli_bridge import CLIPluginBridge
from core.switch_route_validator import SwitchRouteValidator
from core.llm_config import (
    LLMConfig,
    LLMConfigError,
    apply_llm_command,
    default_llm_config,
)
from core.llm_front_door import resolve_llm_front_door
from core.llm_runtime_front_door import (
    format_llm_front_door_result,
    is_llm_config_command,
    is_llm_help_command,
    llm_config_args,
    llm_help_text,
)

# ============================================================
# COMMAND REGISTRY
# ============================================================

class CommandRegistry:
    def __init__(self) -> None:
        self.commands = self.build_default_commands()

    def build_default_commands(self) -> Dict[str, Dict[str, Any]]:
        items = [
            {"name": "system.help", "route": "system", "description": "Show readable help.", "args": {}, "examples": ["/help", "/commands"]},
            {"name": "system.commands", "route": "system", "description": "Show command registry.", "args": {}, "examples": ["/commands"]},
            {"name": "system.state", "route": "system", "description": "Show current state.", "args": {}, "examples": ["/state"]},
            {"name": "system.save", "route": "system", "description": "Save session.", "args": {"name": "string optional"}, "examples": ["/save"]},
            {"name": "system.load", "route": "system", "description": "Load session.", "args": {"name": "string optional"}, "examples": ["/load"]},
            {"name": "system.quit", "route": "system", "description": "Quit host.", "args": {}, "examples": ["/quit", "/exit"]},
            {"name": "system.set_streaming", "route": "system", "description": "Enable/disable streaming.", "args": {"enabled": "bool"}, "examples": ["/stream_on", "/stream_off"]},
            {"name": "system.set_raw_json", "route": "system", "description": "Enable/disable raw JSON tool panes.", "args": {"enabled": "bool"}, "examples": ["/raw_on", "/raw_off"]},
            {"name": "system.guard", "route": "system", "description": "Show output/runaway guard settings and last stop reason.", "args": {}, "examples": ["/guard"]},
            {"name": "system.clear_tui", "route": "system", "description": "Clear the TUI conversation pane.", "args": {}, "examples": ["/clear"]},
            {"name": "system.validation_error", "route": "system", "description": "Show a readable validation error.", "args": {"message": "string", "examples": "list optional"}, "examples": []},
            {"name": "system.patch", "route": "system", "description": "Route /patch commands to the patch runner front door.", "args": {"command": "string"}, "examples": ["/patch dry-run ~/Downloads/example.zip", "/patch replay reports/patch-runs/latest/run.json"]},
            {"name": "system.sources", "route": "system", "description": "Show sources from the last grounded answer or web action.", "args": {}, "examples": ["/sources"]},
            {"name": "system.grounding", "route": "system", "description": "Show the last grounding query plan, accepted sources, weak sources, and fetched pages.", "args": {}, "examples": ["/grounding"]},
            {"name": "system.last", "route": "system", "description": "Show compact information about the last command, plan, result, and source state.", "args": {}, "examples": ["/last"]},
            {"name": "system.plan_last", "route": "system", "description": "Show the last shared plan in readable form.", "args": {}, "examples": ["/plan_last"]},
            {"name": "system.switch", "route": "system", "description": "Inspect the read-only switch matrix.", "args": {"args_text": "string optional"}, "examples": ["/switch status", "/switch list --format json", "/switch plan systemd.ssh.restart --format json"]},
            {"name": "system.last_json", "route": "system", "description": "Show raw last_result JSON explicitly.", "args": {}, "examples": ["/last_json"]},
            {"name": "system.plugins", "route": "system", "description": "List loaded plugins.", "args": {}, "examples": ["/plugins"]},
            {"name": "system.reload_plugins", "route": "system", "description": "Reload plugins from the plugins directory.", "args": {}, "examples": ["/reload_plugins"]},
            {"name": "system.switches", "route": "system", "description": "List plugin-owned /switch aliases and switchable commands.", "args": {"query": "string optional"}, "examples": ["/switches", "/switches comic"]},
            {"name": "system.switch", "route": "system", "description": "Dispatch one plugin command through the plugin-owned /switch registry.", "args": {"expression": "string"}, "examples": ["/switch comic status", "/switch mega.comic.compile horror cover"]},
            {"name": "system.config", "route": "system", "description": "Show loaded external config summary.", "args": {}, "examples": ["/config"]},
            {"name": "system.metadata", "route": "system", "description": "Show loaded agent metadata.", "args": {}, "examples": ["/metadata"]},
            {"name": "system.identity", "route": "system", "description": "Answer local identity questions from loaded metadata.", "args": {"question": "string optional"}, "examples": ["/identity", "/identity who are you?", "/identity what is your name?"]},
            {"name": "system.llm", "route": "system", "description": "Resolve the switch-backed LLM front door.", "args": {"args_text": "string optional"}, "examples": ["/llm models", "/llm choose llama3:8b", "/llm chat hello"]},
            {"name": "system.prompts", "route": "system", "description": "Show loaded prompt config summary.", "args": {}, "examples": ["/prompts"]},
            {"name": "system.reload_config", "route": "system", "description": "Reload external config, prompts, metadata, and personalities.", "args": {}, "examples": ["/reload_config"]},
            {"name": "system.personality", "route": "system", "description": "Show the active behavior preset.", "args": {}, "examples": ["/personality"]},
            {"name": "system.personalities", "route": "system", "description": "List available behavior presets.", "args": {}, "examples": ["/personalities"]},
            {"name": "system.set_personality", "route": "system", "description": "Set the active behavior preset.", "args": {"name": "string"}, "examples": ["/set_personality james"]},
            {"name": "system.summon", "route": "system", "description": "Activate or add a roleplay/persona summon overlay.", "args": {"payload": "string or JSON"}, "examples": ["/summon \"You are Zara Vex...\""]},
            {"name": "chat.summon_prompt", "route": "chat", "description": "Send a prompt through the active summoned persona context.", "args": {"message": "string"}, "examples": ["/summon prompt answer as the active persona"]},
            {"name": "system.unsummon", "route": "system", "description": "Clear active summon overlays.", "args": {}, "examples": ["/unsummon", "/summon clear"]},
            {"name": "system.summon_status", "route": "system", "description": "Show the active summon overlay.", "args": {}, "examples": ["/summon_status"]},
            {"name": "chat.reply", "route": "chat", "description": "Legacy internal LLM reply lane.", "args": {"message": "string optional"}, "examples": ["/prompt write a plan"]},
            {"name": "chat.raw_prompt", "route": "chat", "description": "Raw prompt lane for /prompt only. No grounding, search, scrape, or context assembly.", "args": {"message": "string"}, "examples": ["/prompt write a plan"]},
            {"name": "chat.grounded_reply", "route": "chat", "description": "Grounded answer lane for /ground. Collects evidence before answering.", "args": {"message": "string"}, "examples": ["/prompt write a plan", "/ground what is quantum computing?", "/summon prompt hello"]},
            {"name": "chat.prompt", "route": "chat", "description": "Explicit prompt to the LLM from the contextual slash prompt lanes.", "args": {"message": "string"}, "examples": ["/prompt write a plan", "/ground what is quantum computing?", "/summon prompt hello"]},
            {"name": "chat.contextual_reply", "route": "chat", "description": "Answer a follow-up using recent search/page/summary/chat context.", "args": {"message": "string"}, "examples": ["who directed it?", "what did that page say?", "where is the repo?"]},

            {"name": "chat.grounded_reply", "route": "chat", "description": "Wikipedia-first factual answer with web fallback; say unknown when ungrounded.", "args": {"message": "string", "query": "string optional", "allow_web_fallback": "bool optional"}, "examples": ["who directed Pie 2018", "/ground what is quantum computing"]},
            {"name": "memory.remember", "route": "memory", "description": "Save a local memory note.", "args": {"title": "string", "text": "string", "tags": "list optional"}, "examples": ["remember that the agent uses deterministic routing", "/remember title :: note"]},
            {"name": "memory.retrieve", "route": "memory", "description": "Search local memory.", "args": {"query": "string", "k": "int optional"}, "examples": ["search my memory for routing", "/memory routing"]},
            {"name": "memory.list", "route": "memory", "description": "List recent memory notes.", "args": {"limit": "int optional"}, "examples": ["/memory_list"]},
            {"name": "memory.clear", "route": "memory", "description": "Clear all memory notes.", "args": {}, "examples": ["/memory_clear"]},
            {"name": "fs.pwd", "route": "tool", "description": "Show the agent working directory.", "args": {}, "examples": ["/fs pwd", "show current directory"]},
            {"name": "fs.ls", "route": "tool", "description": "List files in a safe project-relative directory.", "args": {"path": "string optional"}, "examples": ["/fs ls", "show me the files in the current project directory"]},
            {"name": "fs.read", "route": "tool", "description": "Read a small text file from a safe project-relative path.", "args": {"path": "string"}, "examples": ["/fs read tests.sh"]},
            {"name": "python.run", "route": "tool", "description": "Run a short Python snippet in a temporary file with a timeout.", "args": {"code": "string"}, "examples": ["/python print('hello')", "write and run a short Python script"]},
            {"name": "shell.run", "route": "tool", "description": "Run a read-only allowlisted shell command.", "args": {"command": "string"}, "examples": ["/shell pwd", "/shell ls -la"]},
            {"name": "cli.list", "route": "tool", "description": "List manifest-driven CLI bridge tools.", "args": {}, "examples": ["/tool", "/tool list"]},
            {"name": "cli.show", "route": "tool", "description": "Show one CLI bridge manifest.", "args": {"tool_id": "string"}, "examples": ["/tool show mega.conan.story"]},
            {"name": "cli.help", "route": "tool", "description": "Run --help for one CLI bridge tool.", "args": {"tool_id": "string"}, "examples": ["/tool help mega.conan.story"]},
            {"name": "cli.scan", "route": "tool", "description": "Scan a project-local folder and generate draft CLI manifests.", "args": {"path": "string"}, "examples": ["/tool scan external CLI payloads"]},
            {"name": "cli.run", "route": "tool", "description": "Run a manifest-driven CLI tool with allowed args.", "args": {"tool_id": "string", "args_text": "string optional"}, "examples": ["/tool mega.conan.story", "/tool mega.sd.json.tool manifest"]},
            {"name": "cli.pipeline", "route": "tool", "description": "Run one CLI tool and send its stdout to an explicit sink such as LLM chat or A1111 txt2img.", "args": {"source_tool_id": "string optional", "source_args_text": "string optional", "source": "tool|last_cli_stdout", "sink": "llm|a1111", "sink_args": "dict optional"}, "examples": ["create comic book prompt send to a1111", "render it with a1111 and open", "write a conan story"]},
            {"name": "web.search", "route": "web", "description": "Search the web and synthesize a readable answer.", "args": {"query": "string", "max_results": "int optional"}, "examples": ["search imdb for pie 2018", "/web search pyTermTk docs"]},
            {"name": "web.fetch", "route": "web", "description": "Fetch a URL, extract text/title/links.", "args": {"url": "string"}, "examples": ["/web fetch https://example.com"]},
            {"name": "scrape.extract", "route": "scrape", "description": "Scrape and extract content from one URL.", "args": {"url": "string"}, "examples": ["/scrape https://example.com"]},
            {"name": "web.extract_links", "route": "web", "description": "Extract links from last page or URL.", "args": {"url": "string optional"}, "examples": ["/web links"]},
            {"name": "web.follow_link", "route": "web", "description": "Follow numbered link from last page.", "args": {"link_index": "int"}, "examples": ["/web follow 3"]},
            {"name": "web.summarize", "route": "web", "description": "Summarize current or provided URL.", "args": {"url": "string optional"}, "examples": ["/web summarize"]},
            {"name": "web.search_and_summarize", "route": "web", "description": "Search, fetch top result, summarize.", "args": {"query": "string", "max_results": "int optional"}, "examples": ["/web searchsum Python requests streaming"]},
            {"name": "plugin.run", "route": "plugin", "description": "Run a loaded plugin command.", "args": {"command": "string", "args_text": "string optional", "args": "dict optional"}, "examples": ["/plugin example.echo hello"]},
            {"name": "agent.router_explain", "route": "agent", "description": "Explain the local agent router from built-in project context.", "args": {"message": "string optional"}, "examples": ["explain what a router does in this agent"]},
            {"name": "agent.noop", "route": "agent", "description": "Do nothing.", "args": {}, "examples": ["do nothing"]},
        ]
        return {item["name"]: item for item in items}

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        return self.commands.get(name)

    def names(self) -> List[str]:
        return sorted(self.commands.keys())

    def route_for(self, command: str) -> str:
        item = self.get(command)
        if item:
            return str(item.get("route") or command.split(".", 1)[0])
        return command.split(".", 1)[0] if "." in command else "chat"

    def command_manifest(self) -> str:
        compact = []
        for name in self.names():
            item = self.commands[name]
            compact.append({
                "name": item["name"],
                "route": item["route"],
                "description": item["description"],
                "args": item["args"],
                "examples": item["examples"][:3],
            })
        return json.dumps(compact, indent=2, ensure_ascii=False)

    def readable_help(self) -> str:
        return """Agent commands:

System:
  /help
  /commands
  /state
  /clear
  /save [session.json]
  /load [session.json]
  /stream_on
  /stream_off
  /raw_on
  /raw_off
  /quit

Inspection:
  /sources
  /grounding
  /last
  /plan_last
  /last_json
  /config
  /metadata
  /identity
  /personality
  /personalities
  /set_personality <behavior preset name>
  /summon <persona prompt or JSON>
  /summon prompt <message>
  /summon list
  /summon clear
  /unsummon
  /summon_status
  /prompts
  /reload_config

Primary LLM paths:
  /prompt <message>             Direct base LLM; bypasses summoned personas.
  /ground <factual question>    Primary grounded/RAG path and evidence builder.

Persona prompts:
  /summon prompt <message>      Send a prompt to the active summoned persona(s).

Legacy answer-like compatibility commands are unwired.

Legacy AgentSpec/AgentScript planning commands are unwired.

Legacy answer-like prompt templates are unwired. Use the three LLM lanes above.

Patch:
  /patch dry-run <patch.zip>
  /patch apply <patch.zip>
  /patch replay <reports/.../run.json>
  /patch status

Memory:
  /remember <title> :: <text>
  /memory <query>
  /memory_list
  /memory_clear

Local tools:
  /fs pwd
  /fs ls [path]
  /fs read <path>
  /python <short Python code>
  /shell <read-only allowlisted command>
  /tool [list]
  /tool scan <path>
  /tool show <id>
  /tool help <id>
  /tool <id> [allowed args...]

Web:
  /web search <query>
  /web fetch <url>
  /web links
  /web follow <index>
  /web summarize [url]
  /web searchsum <query>

Scrape:
  /scrape <url>
  /scrape extract <url>

TUI local controls:
  /debug_on
  /debug_off
  /timestamps_on
  /timestamps_off
  /history

Plugins:
  /plugins
  /reload_plugins
  /switches [query]
  /switch <plugin-or-alias> <action-or-command> [args]
  /plugin <plugin.command> [text args]
  /plugin_json <plugin.command> <json args>

Grounding policy:
  /ground is the primary grounded/RAG path and evidence-builder surface.
  /summon controls persona/session style only; use /summon prompt for persona-routed prompting.
  /prompt remains direct and does not use summoned persona context.
  Factual questions use Wikipedia first, then multi-source web fallback.
  If no reliable source is found, the agent says it does not know.
""".strip()


# ============================================================
# OLLAMA CLIENT
# ============================================================

class OllamaClient:
    def __init__(self, base_url: str = DEFAULT_OLLAMA_BASE, model: str = DEFAULT_OLLAMA_MODEL, timeout: int = 180) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.session = requests.Session()

    def _url(self, path: str) -> str:
        path = path if path.startswith("/") else f"/{path}"
        return f"{self.base_url}{path}"

    def health(self) -> bool:
        try:
            return self.session.get(self._url("/api/tags"), timeout=5).ok
        except Exception:
            return False

    def _chat_options(self, *, temperature: float, num_predict: Optional[int] = None, repeat_penalty: Optional[float] = None) -> Dict[str, Any]:
        options: Dict[str, Any] = {"temperature": temperature}
        if num_predict is not None and int(num_predict) > 0:
            options["num_predict"] = int(num_predict)
        if repeat_penalty is not None and float(repeat_penalty) > 0:
            options["repeat_penalty"] = float(repeat_penalty)
        return options

    def chat_once(self, messages: List[Dict[str, str]], *, temperature: float = 0.2, num_predict: Optional[int] = None, repeat_penalty: Optional[float] = None) -> str:
        options = self._chat_options(temperature=temperature, num_predict=num_predict, repeat_penalty=repeat_penalty)
        payload = {"model": self.model, "messages": messages, "stream": False, "options": options}
        r = self.session.post(self._url("/api/chat"), json=payload, timeout=self.timeout)
        if r.status_code == 404:
            prompt = "\n".join(m["content"] for m in messages if m.get("role") != "system")
            system = "\n\n".join(m["content"] for m in messages if m.get("role") == "system")
            r = self.session.post(
                self._url("/api/generate"),
                json={"model": self.model, "prompt": prompt, "system": system, "stream": False, "options": options},
                timeout=self.timeout,
            )
            r.raise_for_status()
            return str(r.json().get("response", "")).strip()
        r.raise_for_status()
        data = r.json()
        if isinstance(data.get("message"), dict):
            return str(data["message"].get("content", "")).strip()
        return str(data.get("response", "")).strip()

    def chat_stream(self, messages: List[Dict[str, str]], *, temperature: float = 0.4, num_predict: Optional[int] = None, repeat_penalty: Optional[float] = None) -> Iterator[str]:
        options = self._chat_options(temperature=temperature, num_predict=num_predict, repeat_penalty=repeat_penalty)
        payload = {"model": self.model, "messages": messages, "stream": True, "options": options}
        r = self.session.post(self._url("/api/chat"), json=payload, timeout=self.timeout, stream=True)
        if r.status_code == 404:
            r.close()
            prompt = "\n".join(m["content"] for m in messages if m.get("role") != "system")
            system = "\n\n".join(m["content"] for m in messages if m.get("role") == "system")
            r2 = self.session.post(
                self._url("/api/generate"),
                json={"model": self.model, "prompt": prompt, "system": system, "stream": True, "options": options},
                timeout=self.timeout,
                stream=True,
            )
            r2.raise_for_status()
            for line in r2.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                token = str(data.get("response") or "")
                if token:
                    yield token
                if data.get("done"):
                    break
            return
        r.raise_for_status()
        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                data = json.loads(line)
            except Exception:
                continue
            token = ""
            if isinstance(data.get("message"), dict):
                token = str(data["message"].get("content") or "")
            elif "response" in data:
                token = str(data.get("response") or "")
            if token:
                yield token
            if data.get("done"):
                break


# ============================================================
# MEMORY STORE
# ============================================================

class MemoryStore:
    def __init__(self) -> None:
        self.items: List[Dict[str, Any]] = []

    def remember(self, title: str, text: str, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        item = {
            "id": f"mem_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            "title": clean_text(title)[:160] or "memory",
            "text": str(text or ""),
            "tags": tags or [],
            "created_at": now_str(),
        }
        self.items.append(item)
        self.items = self.items[-2000:]
        return item

    def retrieve(self, query: str, k: int = MAX_MEMORY_RESULTS) -> List[Dict[str, Any]]:
        qtok = tokenize(query)
        scored: List[Tuple[float, Dict[str, Any]]] = []
        for item in self.items:
            text = f"{item.get('title', '')} {item.get('text', '')} {' '.join(item.get('tags', []))}"
            score = jaccard_score(qtok, tokenize(text))
            if score > 0.0:
                scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"score": round(score, 4), **item} for score, item in scored[:k]]

    def list_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        limit = coerce_int(limit, 20, 1, 200)
        return list(reversed(self.items[-limit:]))

    def clear(self) -> Dict[str, Any]:
        count = len(self.items)
        self.items.clear()
        return {"cleared": count}

    def to_list(self) -> List[Dict[str, Any]]:
        return list(self.items)

    def load_list(self, items: List[Dict[str, Any]]) -> None:
        self.items = [item for item in items if isinstance(item, dict)]


# ============================================================
# HTML PARSERS
# ============================================================

class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.parts: List[str] = []
        self.block_tags = {"p", "div", "section", "article", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td", "th", "blockquote", "pre"}

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas"}:
            self.skip_depth += 1
        elif tag in self.block_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas"} and self.skip_depth > 0:
            self.skip_depth -= 1
        elif tag in self.block_tags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth > 0:
            return
        data = clean_text(html.unescape(data))
        if data:
            self.parts.append(data + " ")

    def text(self) -> str:
        raw = "".join(self.parts)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


class TitleExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.parts.append(data)

    def title(self) -> str:
        return clean_text(" ".join(self.parts))


class LinkExtractor(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: List[Dict[str, str]] = []
        self._current_href: Optional[str] = None
        self._current_text: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() != "a":
            return
        attr = dict(attrs)
        href = (attr.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            return
        href = normalize_url(decode_duckduckgo_url(urljoin(self.base_url, href)))
        if not href:
            return
        self._current_href = href
        self._current_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._current_href:
            return
        text = clean_text(" ".join(self._current_text)) or self._current_href
        existing = {link["url"] for link in self.links}
        if self._current_href not in existing and len(self.links) < MAX_LINKS_PER_PAGE:
            self.links.append({"index": len(self.links), "text": text[:240], "url": self._current_href})
        self._current_href = None
        self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href:
            text = clean_text(data)
            if text:
                self._current_text.append(text)


class DuckDuckGoResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: List[Dict[str, str]] = []
        self._in_result_link = False
        self._result_href = ""
        self._result_text: List[str] = []
        self._in_snippet = False
        self._snippet_text: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr = dict(attrs)
        classes = attr.get("class", "") or ""
        if tag.lower() == "a" and "result__a" in classes:
            self._in_result_link = True
            self._result_href = attr.get("href", "") or ""
            self._result_text = []
        if tag.lower() in {"a", "div"} and "result__snippet" in classes:
            self._in_snippet = True
            self._snippet_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._in_result_link:
            title = clean_text(" ".join(self._result_text))
            url = normalize_url(urljoin("https://duckduckgo.com", decode_duckduckgo_url(self._result_href)))
            if title and url and url not in {r["url"] for r in self.results}:
                self.results.append({"index": len(self.results), "title": title, "url": url, "snippet": ""})
            self._in_result_link = False
            self._result_href = ""
            self._result_text = []
        if self._in_snippet and tag.lower() in {"a", "div"}:
            snippet = clean_text(" ".join(self._snippet_text))
            if snippet and self.results:
                for result in reversed(self.results):
                    if not result.get("snippet"):
                        result["snippet"] = snippet
                        break
            self._in_snippet = False
            self._snippet_text = []

    def handle_data(self, data: str) -> None:
        text = clean_text(data)
        if not text:
            return
        if self._in_result_link:
            self._result_text.append(text)
        if self._in_snippet:
            self._snippet_text.append(text)


# ============================================================
# WEB AGENT
# ============================================================

class WebAgent:
    def __init__(self, timeout: int = 30, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def search(self, query: str, max_results: int = 5, site: Optional[str] = None) -> Dict[str, Any]:
        query = clean_text(query)
        site = clean_text(site or "")
        max_results = coerce_int(max_results, 5, 1, MAX_SEARCH_RESULTS)
        if not query:
            raise RuntimeError("web.search requires query")
        final_query = query
        if site:
            site = site.replace("https://", "").replace("http://", "").strip("/")
            final_query = f"site:{site} {query}"
        url = f"https://duckduckgo.com/html/?q={quote_plus(final_query)}"
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        parser = DuckDuckGoResultParser()
        parser.feed(r.text)
        results = parser.results[:max_results]
        return {
            "query": query,
            "site": site or None,
            "final_query": final_query,
            "backend": "duckduckgo_html",
            "count": len(results),
            "results": results,
            "searched_at": now_str(),
        }

    def fetch(self, url: str, *, allow_private: bool = False) -> Dict[str, Any]:
        url = validate_public_fetch_url(url, allow_private=allow_private)
        r = self.session.get(url, timeout=self.timeout, allow_redirects=True)
        r.raise_for_status()
        content_type = r.headers.get("content-type", "").lower()
        if content_type and not any(kind in content_type for kind in ALLOWED_FETCH_CONTENT_TYPES):
            raise RuntimeError(f"Unsupported content type for text fetch: {content_type}")
        html_text = r.text[:MAX_WEB_HTML_CHARS]
        title = self.extract_title(html_text)
        text = self.html_to_text(html_text)
        links = self.extract_links(html_text, str(r.url))
        return {
            "url": str(r.url),
            "requested_url": url,
            "status_code": int(r.status_code),
            "content_type": content_type,
            "title": title,
            "html_size": len(r.text or ""),
            "text": truncate_text(text, MAX_WEB_TEXT_CHARS),
            "text_preview": truncate_text(text, 1200),
            "links": links[:MAX_LINKS_PER_PAGE],
            "fetched_at": now_str(),
        }

    def extract_title(self, html_text: str) -> str:
        parser = TitleExtractor()
        try:
            parser.feed(html_text or "")
        except Exception:
            pass
        return parser.title()

    def html_to_text(self, html_text: str) -> str:
        parser = TextExtractor()
        try:
            parser.feed(html_text or "")
        except Exception:
            pass
        return parser.text()

    def extract_links(self, html_text: str, base_url: str) -> List[Dict[str, str]]:
        parser = LinkExtractor(base_url)
        try:
            parser.feed(html_text or "")
        except Exception:
            pass
        return parser.links[:MAX_LINKS_PER_PAGE]

    def wikipedia_search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        query = clean_text(query)
        limit = coerce_int(limit, 5, 1, 10)
        if not query:
            raise RuntimeError("wikipedia_search requires query")
        params = {"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": limit, "utf8": 1}
        r = self.session.get(WIKIPEDIA_API_BASE, params=params, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        results = []
        for i, item in enumerate(data.get("query", {}).get("search", [])):
            title = item.get("title", "")
            snippet = re.sub(r"<.*?>", "", item.get("snippet", ""))
            results.append({
                "index": i,
                "title": title,
                "pageid": item.get("pageid"),
                "snippet": html.unescape(clean_text(snippet)),
                "url": f"https://en.wikipedia.org/wiki/{quote_plus(title.replace(' ', '_'))}",
            })
        return {"query": query, "backend": "wikipedia_api", "count": len(results), "results": results, "searched_at": now_str()}

    def wikipedia_summary(self, title: str) -> Dict[str, Any]:
        title = clean_text(title)
        if not title:
            raise RuntimeError("wikipedia_summary requires title")
        url_title = quote_plus(title.replace(" ", "_"))
        url = f"{WIKIPEDIA_REST_BASE}/{url_title}"
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        extract = clean_text(data.get("extract", ""))
        page_url = data.get("content_urls", {}).get("desktop", {}).get("page", f"https://en.wikipedia.org/wiki/{url_title}")
        return {"title": data.get("title", title), "description": data.get("description", ""), "extract": extract, "url": page_url, "source": "wikipedia", "fetched_at": now_str()}

    def wikipedia_grounding(self, query: str) -> Dict[str, Any]:
        search = self.wikipedia_search(query, limit=5)
        results = search.get("results") or []
        if not results:
            return {"ok": False, "source": "wikipedia", "query": query, "reason": "No Wikipedia search results.", "search": search, "summary": None}
        top = results[0]
        try:
            summary = self.wikipedia_summary(top["title"])
        except Exception as exc:
            return {"ok": False, "source": "wikipedia", "query": query, "reason": f"Wikipedia summary fetch failed: {exc}", "search": search, "summary": None}
        if not has_grounding_text(summary.get("extract", "")):
            return {"ok": False, "source": "wikipedia", "query": query, "reason": "Wikipedia summary was too thin to ground an answer.", "search": search, "summary": summary}
        return {"ok": True, "source": "wikipedia", "query": query, "search": search, "summary": summary}




# ============================================================
# NATURAL LANGUAGE -> CLI BRIDGE ROUTING
# ============================================================

NL_TOOL_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
NL_TOOL_INTENT_RE = re.compile(
    r"\b(?:tool|cli|bridge|run|use|call|execute|generate|create|make|list|show|display|help|manifest|scan|keyword|keywords|hashtag|hashtags|visualtag|visualtags|visual\s+tags?|prompt|task|seed)\b",
    re.I,
)


def nl_tool_normalize(text: str) -> str:
    value = str(text or "").lower().replace("stable diffusion", "sd").replace("visual tags", "visualtags")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def nl_tool_tokens(text: str) -> List[str]:
    stop = {"mega", "tool", "tools", "the", "a", "an", "cli", "bridge", "use", "run", "call", "show", "list", "generate", "create", "make", "for", "with", "as", "in", "to", "me"}
    return [tok for tok in nl_tool_normalize(text).split() if tok and tok not in stop]


def nl_tool_aliases(tool: Dict[str, Any]) -> List[str]:
    tool_id = clean_text(tool.get("tool_id") or "")
    name = clean_text(tool.get("name") or "")
    desc = clean_text(tool.get("description") or "")
    raw_aliases = {tool_id, name}
    for raw in [tool_id, name]:
        normalized = raw.replace("mega.", "").replace("mega-", "").replace("_", ".")
        normalized = normalized.replace(".tool", " tool").replace(".story", " story").replace(".json", " json")
        raw_aliases.add(normalized.replace(".", " ").replace("-", " "))
        raw_aliases.add(normalized.replace(" tool", "").replace(".", " ").replace("-", " "))
    if "sd.json" in tool_id or "SD JSON" in name:
        raw_aliases.update({"sd json", "stable diffusion json", "stable diffusion json tool"})
    if tool_id == "mega.conan.story":
        raw_aliases.update({"conan story", "conan story seed", "conan seed"})
    if tool_id == "mega.cyberpunk.story":
        raw_aliases.update({"cyberpunk story", "cyberpunk story seed", "generic cyberpunk story"})
    if tool_id == "mega.vampirepunk.story":
        raw_aliases.update({"vampirepunk story", "vampire story", "vampirepunk story seed"})
    if tool_id == "mega.pulp.story":
        raw_aliases.update({"pulp story", "vintage pulp story", "pulp story seed"})
    if tool_id == "mega.neuromancer.cyberpunk.story":
        raw_aliases.update({"neuromancer story", "neuromancer cyberpunk story", "neuromancer cyberpunk story seed"})
    if "prompt.template" in tool_id:
        raw_aliases.update({"prompt template", "template tool", "prompt template tool"})
    if "visual.style" in tool_id:
        raw_aliases.update({"visual style", "visual style tool"})
    if "portrait" in tool_id:
        raw_aliases.add("portrait tool")
    aliases: List[str] = []
    for alias in raw_aliases:
        cleaned = nl_tool_normalize(alias)
        if cleaned and cleaned not in aliases:
            aliases.append(cleaned)
    return sorted(aliases, key=lambda x: (-len(x.split()), -len(x)))


def nl_tool_score(raw_normalized: str, raw_tokens: List[str], tool: Dict[str, Any]) -> Tuple[int, str]:
    best_score = 0
    best_alias = ""
    for alias in nl_tool_aliases(tool):
        alias_tokens = alias.split()
        if not alias_tokens:
            continue
        score = 0
        if alias in raw_normalized:
            score = 100 + len(alias_tokens) * 15
        elif len(alias_tokens) >= 2 and all(tok in raw_tokens for tok in alias_tokens):
            score = 60 + len(alias_tokens) * 10
        elif len(alias_tokens) == 1 and alias_tokens[0] in raw_tokens:
            score = 25
        if score > best_score:
            best_score = score
            best_alias = alias
    return best_score, best_alias


def nl_tool_count_arg(raw: str, allowed_args: List[str]) -> List[str]:
    if "--count" not in allowed_args and "-c" not in allowed_args:
        return []
    lowered = raw.lower()
    value: Optional[int] = None
    m = re.search(r"\bcount\s+(?:of\s+)?(\d{1,3})\b", lowered) or re.search(r"\b(\d{1,3})\s+(?:items?|records?|stories?|seeds?|examples?)\b", lowered)
    if m:
        value = coerce_int(m.group(1), 1, 1, 100)
    else:
        for word, number in NL_TOOL_NUMBER_WORDS.items():
            if re.search(rf"\b{re.escape(word)}\b", lowered):
                value = number
                break
    return ["--count", str(value)] if value is not None else []


def nl_tool_story_contract_format_args(raw: str, tool: Dict[str, Any], allowed_args: List[str]) -> List[str]:
    """Story-tool NL shortcuts for explicit output contracts.

    Applies only to the contracted story tools and maps clear phrases like
    "generate a cyberpunk story prompt" or "make one pulp story task" to the
    tool-owned --format prompt/task modes. Already-formed prompts/tasks are
    protected before this matcher runs by looks_like_model_ready_prompt_or_task().
    """
    tool_id = clean_text(tool.get("tool_id") or "")
    contracted_story_tools = {
        "mega.conan.story",
        "mega.cyberpunk.story",
        "mega.vampirepunk.story",
        "mega.pulp.story",
        "mega.neuromancer.cyberpunk.story",
    }
    if tool_id not in contracted_story_tools or "--format" not in allowed_args:
        return []
    lowered = raw.lower()
    has_generation_verb = bool(re.search(r"\b(?:generate|create|make|return|output|format|print|use|run)\b", lowered))
    wants_prompt_output = bool(
        re.search(
            r"\b(?:generate|create|make|return|output|format|print|as|in)\s+(?:a\s+|the\s+)?(?:clean\s+)?prompt\b|\bprompt\s+(?:output|format|mode)\b",
            lowered,
        )
        or (has_generation_verb and re.search(r"\bprompt\b", lowered))
    )
    wants_task_output = bool(
        re.search(
            r"\b(?:generate|create|make|return|output|format|print|as|in)\s+(?:a\s+|the\s+)?(?:strict\s+|model-ready\s+|model\s+ready\s+)?task\b|\btask\s+(?:output|format|mode)\b",
            lowered,
        )
        or (has_generation_verb and re.search(r"\btask\b", lowered))
    )
    if wants_task_output:
        return ["--format", "task"]
    if wants_prompt_output:
        return ["--format", "prompt"]
    return []


# Backward-compatible name for older tests/imports; the function now covers all
# contracted story tools, not just Conan.
def nl_tool_conan_format_args(raw: str, tool: Dict[str, Any], allowed_args: List[str]) -> List[str]:
    return nl_tool_story_contract_format_args(raw, tool, allowed_args)


def nl_tool_format_args(raw: str, allowed_args: List[str]) -> List[str]:
    lowered = raw.lower()
    wants_json_output = bool(re.search(r"\b(?:as|in|return|output|format|print)\s+json\b|\bjson\s+(?:output|format)\b", lowered))
    wants_text_output = bool(re.search(r"\b(?:as|in|return|output|format|print)\s+text\b|\btext\s+(?:output|format)\b", lowered))
    if "--format" in allowed_args:
        if wants_json_output:
            return ["--format", "json"]
        if wants_text_output:
            return ["--format", "text"]
    if "--json" in allowed_args and wants_json_output:
        return ["--json"]
    return []


def nl_tool_boolean_args(raw: str, allowed_args: List[str]) -> List[str]:
    lowered = raw.lower()
    pairs = [
        ("--pretty", r"\bpretty\b"),
        ("--prompt-only", r"\bprompt\s+only\b"),
        ("--negative-only", r"\bnegative\s+only\b"),
        ("--selected-only", r"\bselected\s+only\b"),
        ("--output-only", r"\boutput\s+only\b"),
        ("--style-only", r"\bstyle\s+only\b"),
        ("--show-parameters", r"\bshow\s+parameters\b"),
        ("--list-fields", r"\blist\s+fields\b"),
    ]
    return [flag for flag, pattern in pairs if flag in allowed_args and re.search(pattern, lowered)]


def nl_tool_list_target_args(raw: str, allowed_args: List[str]) -> List[str]:
    if "--list-target" not in allowed_args:
        return []
    normalized = nl_tool_normalize(raw)
    toks = set(normalized.split())
    targets = [
        ("keywords", {"keyword", "keywords"}),
        ("hashtags", {"hashtag", "hashtags"}),
        ("visualtags", {"visualtag", "visualtags", "visual", "tags"}),
        ("sections", {"section", "sections"}),
        ("fields", {"field", "fields"}),
        ("families", {"family", "families"}),
    ]
    for target, words in targets:
        if target in normalized or words.intersection(toks):
            return ["--list-target", target]
    return []


def nl_tool_positional_arg(raw: str, allowed_positionals: List[str]) -> List[str]:
    if not allowed_positionals:
        return []
    normalized = nl_tool_normalize(raw)
    if "list" in allowed_positionals and re.search(r"\b(?:list|keywords?|hashtags?|visualtags?|visual\s+tags?|sections?)\b", raw, re.I):
        return ["list"]
    for item in ["manifest", "validate", "inspect", "generate", "render", "template", "schema"]:
        if item in allowed_positionals and re.search(rf"\b{re.escape(item)}\b", normalized):
            return [item]
    for item in allowed_positionals:
        if re.search(rf"\b{re.escape(item)}\b", normalized):
            return [item]
    return []


def build_nl_tool_args(raw: str, tool: Dict[str, Any]) -> str:
    allowed_args = [str(x) for x in tool.get("allowed_args", []) if isinstance(x, str)]
    allowed_positionals = [str(x) for x in tool.get("allowed_positionals", []) if isinstance(x, str)]
    args: List[str] = []
    args.extend(nl_tool_positional_arg(raw, allowed_positionals))
    args.extend(nl_tool_count_arg(raw, allowed_args))
    args.extend(nl_tool_story_contract_format_args(raw, tool, allowed_args))
    if "--format" not in args:
        args.extend(nl_tool_format_args(raw, allowed_args))
    args.extend(nl_tool_list_target_args(raw, allowed_args))
    args.extend(nl_tool_boolean_args(raw, allowed_args))
    return " ".join(shlex.quote(x) for x in args)


MODEL_READY_TASK_MARKER_RE = re.compile(
    r"(?im)^\s*(?:task|instruction|requirements?|rules?|parameters?)\s*:",
)


def looks_like_model_ready_prompt_or_task(raw: str) -> bool:
    """Protect already-formed prompts/tasks from NL -> /tool shortcuts.

    The CLI natural-language mapper should run tools for requests like
    "generate one Conan story seed as json". It should not steal the output of
    those tools after the user pastes a final prompt back into the agent, such
    as "Write a Conan-style story... Requirements: ... Parameters: ...".
    """
    text = str(raw or "").strip()
    if not text:
        return False
    lowered = text.lower()
    line_count = len([line for line in text.splitlines() if line.strip()])

    explicit_task_start = bool(re.match(r"(?is)^\s*(?:task|instruction)\s*:\s*", text))
    has_structured_markers = bool(MODEL_READY_TASK_MARKER_RE.search(text))
    has_parameters = bool(re.search(r"(?im)^\s*parameters?\s*:", text))
    has_requirements_or_rules = bool(re.search(r"(?im)^\s*(?:requirements?|rules?)\s*:", text))
    asks_final_output = bool(re.search(r"\breturn\s+only\b|\boutput\s+only\b|\bfinal\s+(?:answer|story|output)\s+only\b", lowered))
    write_with_parameters = bool(re.search(r"\bwrite\b.+\busing\s+(?:these|the)\s+parameters\b", lowered, flags=re.S))

    if explicit_task_start and (has_parameters or has_requirements_or_rules or asks_final_output or line_count >= 3):
        return True
    # /plan and some shell wrappers collapse pasted text to one line; still protect
    # it if it clearly contains prompt/task section labels.
    if has_parameters and (has_requirements_or_rules or asks_final_output or write_with_parameters):
        return True
    if write_with_parameters and (has_structured_markers or asks_final_output):
        return True
    return False



STORY_PIPELINE_TOOL_IDS = {
    "mega.conan.story",
    "mega.cyberpunk.story",
    "mega.vampirepunk.story",
    "mega.pulp.story",
    "mega.neuromancer.cyberpunk.story",
}
A1111_PIPELINE_TOOL_ID = "mega.a1111.webui.tool"


def find_cli_tool_record(cli_tools: Any, tool_id: str) -> Optional[Dict[str, Any]]:
    if not isinstance(cli_tools, list):
        return None
    for tool in cli_tools:
        if isinstance(tool, dict) and clean_text(tool.get("tool_id") or "") == tool_id:
            return tool
    return None


def best_nl_tool_for_pipeline(raw: str, cli_tools: Any, *, include_story: bool) -> Optional[Tuple[int, str, Dict[str, Any]]]:
    if not isinstance(cli_tools, list):
        return None
    normalized = nl_tool_normalize(raw)
    tokens = nl_tool_tokens(raw)
    best: Optional[Tuple[int, str, Dict[str, Any]]] = None
    for tool in cli_tools:
        if not isinstance(tool, dict):
            continue
        tool_id = clean_text(tool.get("tool_id") or "")
        if not include_story and tool_id in STORY_PIPELINE_TOOL_IDS:
            continue
        if tool_id in {A1111_PIPELINE_TOOL_ID, "mega.image.open.tool"}:
            continue
        score, alias = nl_tool_score(normalized, tokens, tool)
        if score <= 0:
            continue
        if not include_story and any(word in tool_id for word in ["comic", "portrait", "anime", "visual", "photo", "ink", "sd.", "prompt", "monster", "deity"]):
            score += 20
        if best is None or score > best[0]:
            best = (score, alias, tool)
    return best if best and best[0] >= 60 else None


def nl_wants_a1111_sink(raw: str) -> bool:
    lowered = raw.lower()

    # Only explicit render/send-to-image language should enter the A1111
    # pipeline.  Do not treat every occurrence of "stable diffusion" as an
    # image-render request: phrases like "use the stable diffusion json tool
    # to list keywords" are normal /tool calls and must not be piped to A1111.
    explicit_a1111 = bool(re.search(r"\b(?:a1111|a111|automatic1111|sd\s+webui|webui)\b", lowered))
    direct_image = bool(
        re.search(r"\b(?:render|generate|make|create)\b", lowered)
        and re.search(r"\b(?:image|picture|pic|art|illustration)\b", lowered)
    )
    stable_diffusion_render = bool(
        re.search(r"\b(?:render|generate|make|create|send|pass|use)\b", lowered)
        and re.search(r"\bstable\s+diffusion\b", lowered)
        and re.search(r"\b(?:prompt|image|picture|pic|art|illustration|txt2img)\b", lowered)
        and not re.search(r"\b(?:list|show|help|manifest|keyword|keywords|hashtag|hashtags|visualtag|visualtags|section|sections)\b", lowered)
    )
    return explicit_a1111 or direct_image or stable_diffusion_render


def nl_wants_llm_sink(raw: str) -> bool:
    lowered = raw.lower()
    return bool(
        re.search(r"\b(?:send|use|pass)\b.+\b(?:llm|model|chat)\b", lowered)
        or re.search(r"\b(?:write|draft|compose|complete|tell)\b.+\b(?:story|scene|prose)\b", lowered)
        or re.search(r"\b(?:write|draft|compose|complete)\s+(?:it|that|the\s+last)\b", lowered)
    )


def nl_has_contract_output_word(raw: str) -> bool:
    return bool(re.search(r"\b(?:prompt|task|seed|json|text|manifest|help|list|show)\b", raw.lower()))


def nl_pipeline_sink_args(raw: str, sink: str) -> Dict[str, Any]:
    lowered = raw.lower()
    args: Dict[str, Any] = {}
    if sink == "a1111":
        args["open"] = bool(re.search(r"\b(?:open|show|view|display)\b", lowered))
        args["dry_run"] = bool(re.search(r"\b(?:dry\s*run|dry-run|preview\s+payload|no\s+generate)\b", lowered))
        for flag, pattern in [("steps", r"\bsteps?\s+(\d{1,3})\b"), ("width", r"\bwidth\s+(\d{2,4})\b"), ("height", r"\bheight\s+(\d{2,4})\b")]:
            m = re.search(pattern, lowered)
            if m:
                args[flag] = int(m.group(1))
    return args


def extract_direct_a1111_prompt(raw: str) -> str:
    """Extract the subject from explicit direct-render requests.

    This is deliberately narrow so it does not steal normal chat.
    Examples: render image of X, create a picture of X, make art of X.
    """
    text = clean_text(raw)
    if not text:
        return ""
    patterns = [
        r"(?is)^\s*(?:render|generate|make|create)\s+(?:an?\s+)?(?:image|picture|pic|art|illustration)\s+(?:of|showing|depicting|for)\s+(.+?)\s*$",
        r"(?is)^\s*(?:render|generate|make|create)\s+(.+?)\s+(?:as|into)\s+(?:an?\s+)?(?:image|picture|pic|art|illustration)\s*$",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if not m:
            continue
        prompt = clean_text(m.group(1))
        prompt = re.sub(r"\b(?:with\s+)?(?:a1111|automatic1111|stable\s+diffusion|sd\s+webui|webui)\b", "", prompt, flags=re.I)
        prompt = re.sub(r"\b(?:dry\s*run|dry-run|open|show|view|display)\b", "", prompt, flags=re.I)
        prompt = clean_text(prompt.strip(" .,:;-"))
        if prompt and not looks_like_model_ready_prompt_or_task(prompt):
            return prompt
    return ""


def match_cli_pipeline_natural_language(raw: str, cli_tools: Any) -> Optional[Dict[str, Any]]:
    """Small deterministic tool-output pipeline matcher.

    Explicit /tool stays the stable interface. This only handles obvious sink
    language: prompt-like tool output -> A1111, or story tool task -> LLM.
    """
    text = str(raw or "").strip()
    if not text or not isinstance(cli_tools, list):
        return None
    if looks_like_model_ready_prompt_or_task(text):
        return None
    lowered = text.lower()
    available_a1111 = find_cli_tool_record(cli_tools, A1111_PIPELINE_TOOL_ID) is not None

    if available_a1111:
        direct_prompt = extract_direct_a1111_prompt(text)
        if direct_prompt:
            return {"command": "cli.pipeline", "intent": "cli_pipeline_direct_text_to_a1111", "args": {"source": "direct_text", "source_text": direct_prompt, "sink": "a1111", "sink_args": nl_pipeline_sink_args(text, "a1111")}, "confidence": 0.92, "matched_alias": "direct text -> a1111"}

    if available_a1111 and (
        re.search(r"\b(?:render|generate|make|create|send|pass)\b.+\b(?:it|that|last|previous)\b.+\b(?:a1111|automatic1111|stable\s+diffusion|image|picture|art|prompt)\b", lowered)
        or re.search(r"\b(?:render|generate|make|create)\s+(?:it|that|this)(?:\s+(?:with\s+)?(?:a1111|automatic1111|stable\s+diffusion|sd\s+webui|webui))?(?:\s+(?:dry\s*run|dry-run|open|show|view|display))*\s*$", lowered)
        or re.search(r"\b(?:send|pass|use)\s+(?:it|that|this)\s+(?:to|with)\s+(?:a1111|automatic1111|stable\s+diffusion|sd\s+webui|webui)\b", lowered)
    ):
        return {"command": "cli.pipeline", "intent": "cli_pipeline_last_to_a1111", "args": {"source": "last_cli_stdout", "sink": "a1111", "sink_args": nl_pipeline_sink_args(text, "a1111")}, "confidence": 0.91, "matched_alias": "last tool output -> a1111"}

    if re.search(r"\b(?:write|draft|compose|complete|send|pass|use)\b.+\b(?:it|that|last|previous)\b.+\b(?:llm|model|chat|story|prose|scene)\b", lowered):
        return {"command": "cli.pipeline", "intent": "cli_pipeline_last_to_llm", "args": {"source": "last_cli_stdout", "sink": "llm", "sink_args": {}}, "confidence": 0.9, "matched_alias": "last tool output -> llm"}

    if available_a1111 and nl_wants_a1111_sink(text):
        best = best_nl_tool_for_pipeline(text, cli_tools, include_story=False)
        if best:
            _score, alias, tool = best
            tool_id = clean_text(tool.get("tool_id") or "")
            return {"command": "cli.pipeline", "intent": "cli_pipeline_tool_to_a1111", "args": {"source": "tool", "source_tool_id": tool_id, "source_args_text": build_nl_tool_args(text, tool), "sink": "a1111", "sink_args": nl_pipeline_sink_args(text, "a1111")}, "confidence": 0.88, "matched_alias": f"{alias} -> a1111"}

    if nl_wants_llm_sink(text) or (re.search(r"\b(?:generate|create|make)\b", lowered) and re.search(r"\bstory\b", lowered) and not nl_has_contract_output_word(text)):
        best = best_nl_tool_for_pipeline(text, cli_tools, include_story=True)
        if best:
            _score, alias, tool = best
            tool_id = clean_text(tool.get("tool_id") or "")
            if tool_id in STORY_PIPELINE_TOOL_IDS:
                allowed = [str(x) for x in tool.get("allowed_args", []) if isinstance(x, str)]
                source_args_list = nl_tool_count_arg(text, allowed) + ["--format", "task"]
                source_args = " ".join(shlex.quote(x) for x in source_args_list)
                return {"command": "cli.pipeline", "intent": "cli_pipeline_story_to_llm", "args": {"source": "tool", "source_tool_id": tool_id, "source_args_text": source_args, "sink": "llm", "sink_args": {}}, "confidence": 0.88, "matched_alias": f"{alias} -> llm"}
    return None


def clean_code_feature_name(value: str) -> str:
    name = clean_text(value)
    name = re.sub(r"\b(?:please|thanks|thank\s+you)\b", "", name, flags=re.I)
    name = re.sub(r"\b(?:in|inside|from)\s+(?:the\s+)?(?:codebase|project|repo|repository)\b", "", name, flags=re.I)
    name = re.sub(r"[?.!]+$", "", name).strip(" :;-\t\n\r\"'")
    return clean_text(name)


def match_code_feature_tool_natural_language(raw: str, cli_tools: Any) -> Optional[Dict[str, Any]]:
    """Small deterministic shortcuts for code.feature.tool.

    Explicit /tool remains the stable interface. These shortcuts only match
    obvious code-feature inspection requests and intentionally do not catch
    general coding prompts like "write code" or "explain this code".
    """
    text = str(raw or "").strip()
    if not text or not isinstance(cli_tools, list):
        return None
    if looks_like_model_ready_prompt_or_task(text):
        return None
    tool = find_cli_tool_record(cli_tools, "code.feature.tool")
    if not tool:
        return None

    lowered = text.lower()

    if re.search(r"\bcode\s+feature(?:\s+tool)?\s+(?:status|ready)\b", lowered) or re.search(r"\bis\s+(?:the\s+)?code\s+feature\s+tool\s+ready\b", lowered):
        return {
            "command": "cli.run",
            "intent": "code_feature_status_nl",
            "args": {"tool_id": "code.feature.tool", "args_text": "status --json --pretty"},
            "confidence": 0.93,
            "matched_alias": "code feature status",
        }

    m_extract = (
        re.search(r"\b(?:extract|get|show|prepare)\s+(?:the\s+)?(?:code\s+)?context\s+for\s+(.+?)\s*$", text, re.I)
        or re.search(r"\b(?:extract|get|show|prepare)\s+(.+?)\s+code\s+context\s*$", text, re.I)
    )
    if m_extract:
        feature = clean_code_feature_name(m_extract.group(1))
        if feature:
            args = [
                "extract", "--repo", ".", "--feature", feature, "--markdown",
                "--max-code-files", "5", "--max-lines-per-file", "120",
            ]
            return {
                "command": "cli.run",
                "intent": "code_feature_extract_nl",
                "args": {"tool_id": "code.feature.tool", "args_text": " ".join(shlex.quote(x) for x in args)},
                "confidence": 0.91,
                "matched_alias": "code feature extract",
            }

    m_files = re.search(r"\bwhat\s+files\s+implement\s+(.+?)\s*$", text, re.I)
    if m_files:
        feature = clean_code_feature_name(m_files.group(1))
        if feature:
            args = ["map", "--repo", ".", "--markdown", "--feature", feature]
            return {
                "command": "cli.run",
                "intent": "code_feature_map_feature_nl",
                "args": {"tool_id": "code.feature.tool", "args_text": " ".join(shlex.quote(x) for x in args)},
                "confidence": 0.9,
                "matched_alias": "code feature files implement",
            }

    m_feature = (
        re.search(r"\b(?:show|map|display)\s+(?:me\s+)?(?:the\s+)?code\s+feature\s+(.+?)\s*$", text, re.I)
        or re.search(r"\b(?:show|map|display)\s+(?:me\s+)?(?:the\s+)?(.+?)\s+feature\s*$", text, re.I)
    )
    if m_feature:
        feature = clean_code_feature_name(m_feature.group(1))
        if feature and feature.lower() not in {"code", "features", "feature"}:
            args = ["map", "--repo", ".", "--markdown", "--feature", feature]
            return {
                "command": "cli.run",
                "intent": "code_feature_map_feature_nl",
                "args": {"tool_id": "code.feature.tool", "args_text": " ".join(shlex.quote(x) for x in args)},
                "confidence": 0.9,
                "matched_alias": "code feature map one",
            }

    if (
        re.search(r"\b(?:map|show|list|display)\s+(?:me\s+)?(?:the\s+)?code\s+features?\b", text, re.I)
        or re.search(r"\bwhat\s+features\s+(?:are|exist|live)\s+(?:in|inside)\s+(?:this\s+)?(?:codebase|project|repo|repository)\b", text, re.I)
    ):
        return {
            "command": "cli.run",
            "intent": "code_feature_map_all_nl",
            "args": {"tool_id": "code.feature.tool", "args_text": "map --repo . --markdown"},
            "confidence": 0.9,
            "matched_alias": "code feature map all",
        }

    return None


# ============================================================
# TOOL FAMILY NLP PREFERENCE
# ============================================================

_TOOL_FAMILIES_PATH_TEXT = "data_agent/nlp/tool_families.json"
_ACTIVE_TOOL_FAMILY_PATH_TEXT = "data_agent/runtime/active_tool_family.json"


def _load_tool_family_preference_data():
    import json
    from pathlib import Path

    path = Path(_TOOL_FAMILIES_PATH_TEXT)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _active_tool_family_preference_name() -> str:
    import json
    from pathlib import Path

    path = Path(_ACTIVE_TOOL_FAMILY_PATH_TEXT)
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    return clean_text(data.get("family") or "").lower()


def _active_tool_family_preference_tool_ids():
    family = _active_tool_family_preference_name()
    if not family:
        return set()

    data = _load_tool_family_preference_data()
    families = data.get("families") if isinstance(data, dict) else {}
    if not isinstance(families, dict):
        return set()

    spec = families.get(family)
    if not isinstance(spec, dict):
        return set()

    raw_tool_ids = spec.get("tool_ids")
    if not isinstance(raw_tool_ids, list):
        return set()

    return {
        clean_text(item)
        for item in raw_tool_ids
        if isinstance(item, str) and clean_text(item)
    }


def _active_tool_family_score_bonus(tool_id: str) -> int:
    clean_id = clean_text(tool_id)
    if not clean_id:
        return 0
    return 35 if clean_id in _active_tool_family_preference_tool_ids() else 0

def match_cli_tool_natural_language(raw: str, cli_tools: Any) -> Optional[Dict[str, Any]]:
    text = str(raw or "").strip()
    if not text or not isinstance(cli_tools, list):
        return None
    if looks_like_model_ready_prompt_or_task(text):
        return None
    normalized = nl_tool_normalize(text)
    tokens = nl_tool_tokens(text)
    if re.search(r"\blist\b.+\b(?:cli|bridge|tools)\b", text, re.I) or re.search(r"\bwhat\s+(?:cli\s+)?tools\b", text, re.I) or re.search(r"\bavailable\s+(?:cli\s+)?tools\b", text, re.I):
        verbose = bool(re.search(r"\b(?:verbose|full|details?|detailed)\b", text, re.I))
        return {"command": "cli.list", "intent": "cli_natural_list", "args": {"verbose": verbose}, "confidence": 0.92, "matched_alias": "tool list"}
    m_scan = re.search(r"\bscan\s+(?P<path>[A-Za-z0-9_./-]+)\s+(?:for\s+)?(?:cli\s+)?tools?\b", text, re.I) or re.search(r"\bscan\s+(?:the\s+)?(?:folder|directory)\s+(?P<path>[A-Za-z0-9_./-]+)\b", text, re.I)
    if m_scan:
        return {"command": "cli.scan", "intent": "cli_natural_scan", "args": {"path": m_scan.group("path")}, "confidence": 0.9, "matched_alias": "scan"}
    code_feature_match = match_code_feature_tool_natural_language(text, cli_tools)
    if code_feature_match:
        return code_feature_match
    if not NL_TOOL_INTENT_RE.search(text):
        return None
    best: Optional[Tuple[int, str, Dict[str, Any]]] = None
    for tool in cli_tools:
        if not isinstance(tool, dict):
            continue
        tool_id = clean_text(tool.get("tool_id") or "")
        score, alias = nl_tool_score(normalized, tokens, tool)
        if score <= 0:
            continue
        score += _active_tool_family_score_bonus(tool_id)
        if best is None or score > best[0]:
            best = (score, alias, tool)
    if not best or best[0] < 60:
        return None
    score, alias, tool = best
    tool_id = clean_text(tool.get("tool_id") or "")
    lowered = text.lower()
    if re.search(r"\bhelp\b", lowered):
        return {"command": "cli.help", "intent": "cli_natural_help", "args": {"tool_id": tool_id}, "confidence": 0.88, "matched_alias": alias}
    if re.search(r"\b(?:show|display|inspect)\b", lowered) and re.search(r"\b(?:bridge\s+)?(?:tool\s+)?manifest|tool\s+config|tool\s+info\b", lowered):
        return {"command": "cli.show", "intent": "cli_natural_show", "args": {"tool_id": tool_id}, "confidence": 0.86, "matched_alias": alias}
    args_text = build_nl_tool_args(text, tool)
    return {"command": "cli.run", "intent": "cli_natural_run", "args": {"tool_id": tool_id, "args_text": args_text}, "confidence": min(0.95, 0.7 + score / 500.0), "matched_alias": alias}



# ============================================================
# IMPORTED TOOL EXACT NLP ALIASES
# ============================================================

_IMPORTED_TOOL_EXACT_ALIAS_PATH_TEXT = "data_agent/nlp/imported_tool_exact_aliases_01.json"
_IMPORTED_TOOL_EXACT_ALIAS_CACHE = None
_BLOCKED_IMPORTED_TOOL_ALIAS_IDS = {
    "bundle.mega.sd.json",
}


def _imported_tool_alias_clean(value):
    return str(value or "").strip()


def _active_cli_manifest_exists_for_tool_id(tool_id):
    from pathlib import Path

    safe_tool_id = _imported_tool_alias_clean(tool_id)
    if not safe_tool_id or not safe_tool_id.startswith("bundle."):
        return False
    manifest_path = Path("data_agent/plugins/cli") / f"{safe_tool_id}.json"
    return manifest_path.is_file()


def _load_imported_tool_exact_aliases():
    import json
    from pathlib import Path

    global _IMPORTED_TOOL_EXACT_ALIAS_CACHE
    if _IMPORTED_TOOL_EXACT_ALIAS_CACHE is not None:
        return list(_IMPORTED_TOOL_EXACT_ALIAS_CACHE)

    aliases = []
    path = Path(_IMPORTED_TOOL_EXACT_ALIAS_PATH_TEXT)
    if not path.is_file():
        _IMPORTED_TOOL_EXACT_ALIAS_CACHE = []
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _IMPORTED_TOOL_EXACT_ALIAS_CACHE = []
        return []

    raw_aliases = data.get("aliases") if isinstance(data, dict) else []
    if not isinstance(raw_aliases, list):
        _IMPORTED_TOOL_EXACT_ALIAS_CACHE = []
        return []

    for item in raw_aliases:
        if not isinstance(item, dict):
            continue
        phrase = _imported_tool_alias_clean(item.get("phrase"))
        tool_id = _imported_tool_alias_clean(item.get("tool_id"))
        args_text = _imported_tool_alias_clean(item.get("args_text"))
        if not phrase or not tool_id:
            continue
        if not tool_id.startswith("bundle."):
            continue
        if tool_id in _BLOCKED_IMPORTED_TOOL_ALIAS_IDS:
            continue
        if not _active_cli_manifest_exists_for_tool_id(tool_id):
            continue
        aliases.append({"phrase": phrase, "tool_id": tool_id, "args_text": args_text})

    _IMPORTED_TOOL_EXACT_ALIAS_CACHE = aliases
    return list(aliases)


def _match_imported_tool_exact_alias(text):
    raw = _imported_tool_alias_clean(text)
    if not raw:
        return None
    lowered = raw.lower()
    for alias in _load_imported_tool_exact_aliases():
        if lowered == _imported_tool_alias_clean(alias.get("phrase")).lower():
            return {"tool_id": alias["tool_id"], "args_text": alias.get("args_text", "")}
    return None

# ============================================================
# REQUEST ROUTER
# ============================================================

class RequestRouter:
    def __init__(self, registry: CommandRegistry) -> None:
        self.registry = registry

    def try_parse_slash_command(self, text: str) -> Optional[RouteDecision]:
        if not text.startswith("/"):
            return None
        command, _, arg = text.partition(" ")
        command = command.lower().strip()
        arg = arg.strip()

        def rd(*, intent: str, route: str, cmd: str, args: Optional[Dict[str, Any]] = None, llm: bool = False) -> RouteDecision:
            return RouteDecision(
                intent=intent,
                route=route,
                confidence=1.0,
                command=cmd,
                args=args or {},
                requires_web=route == "web" or cmd == "chat.grounded_reply",
                requires_memory=route == "memory",
                requires_llm_response=llm,
                rewritten_user_request=arg or text,
                reasoning_summary="Parsed deterministic slash command.",
            )


        if command in LEGACY_UNWIRED_SLASH_COMMANDS:
            return rd(
                intent="legacy_unwired",
                route="system",
                cmd="system.validation_error",
                args={
                    "message": (
                        f"Legacy command is unwired: {command}. "
                        "Use /prompt for direct LLM, /ground for grounded/RAG answers, "
                        "or /summon prompt for persona-routed prompting."
                    ),
                    "command": command,
                    "examples": ["/prompt write a plan", "/ground what is quantum computing?", "/summon prompt hello"],
                },
            )

        if command == "/help": return rd(intent="help", route="system", cmd="system.help")
        if command == "/commands": return rd(intent="commands", route="system", cmd="system.commands")
        if command == "/state": return rd(intent="state", route="system", cmd="system.state")
        if command == "/clear": return rd(intent="clear", route="system", cmd="system.clear_tui")
        if command == "/sources": return rd(intent="sources", route="system", cmd="system.sources")
        if command == "/grounding": return rd(intent="grounding", route="system", cmd="system.grounding")
        if command == "/last": return rd(intent="last", route="system", cmd="system.last")
        if command == "/plan_last": return rd(intent="plan_last", route="system", cmd="system.plan_last")
        if command == "/llm": return rd(intent="llm_front_door", route="system", cmd="system.llm", args={"args_text": arg})
        if command == "/switch": return rd(intent="switch_matrix", route="system", cmd="system.switch", args={"args_text": arg})
        if command == "/last_json": return rd(intent="last_json", route="system", cmd="system.last_json")
        if command == "/config": return rd(intent="config", route="system", cmd="system.config")
        if command == "/metadata": return rd(intent="metadata", route="system", cmd="system.metadata")
        if command == "/identity": return rd(intent="identity", route="system", cmd="system.identity", args={"question": arg or "who are you?"})
        if command == "/prompts": return rd(intent="prompts", route="system", cmd="system.prompts")
        if command == "/reload_config": return rd(intent="reload_config", route="system", cmd="system.reload_config")
        if command == "/personality": return rd(intent="personality", route="system", cmd="system.personality")
        if command == "/personalities": return rd(intent="personalities", route="system", cmd="system.personalities")
        if command == "/set_personality": return rd(intent="set_personality", route="system", cmd="system.set_personality", args={"name": arg})
        if command == "/summon":
            summon_sub, _, summon_rest = arg.partition(" ")
            summon_sub = clean_text(summon_sub).lower()
            summon_rest = summon_rest.strip()
            if summon_sub == "prompt":
                return rd(intent="summon_prompt", route="chat", cmd="chat.summon_prompt", args={"message": summon_rest}, llm=True)
            if summon_sub in {"list", "status"} and not summon_rest:
                return rd(intent="summon_status", route="system", cmd="system.summon_status")
            if summon_sub in {"clear", "reset"} and not summon_rest:
                return rd(intent="unsummon", route="system", cmd="system.unsummon")
            return rd(intent="summon", route="system", cmd="system.summon", args={"payload": arg})
        if command == "/unsummon": return rd(intent="unsummon", route="system", cmd="system.unsummon")
        if command == "/summon_status": return rd(intent="summon_status", route="system", cmd="system.summon_status")
        if command == "/plugins": return rd(intent="plugins", route="system", cmd="system.plugins")
        if command == "/reload_plugins": return rd(intent="reload_plugins", route="system", cmd="system.reload_plugins")
        if command == "/switches": return rd(intent="switches", route="system", cmd="system.switches", args={"query": arg})
        if command == "/switch": return rd(intent="switch", route="system", cmd="system.switch", args={"expression": arg})
        if command == "/plugin":
            sub, _, rest = arg.partition(" ")
            sub = clean_text(sub)
            rest = rest.strip()
            return rd(
                intent="plugin_run",
                route="plugin",
                cmd="plugin.run",
                args={"command": sub, "args_text": rest},
                llm=False,
            )
        if command == "/plugin_json":
            sub, _, rest = arg.partition(" ")
            sub = clean_text(sub)
            payload = extract_first_json_object(rest) or {}
            return rd(
                intent="plugin_run_json",
                route="plugin",
                cmd="plugin.run",
                args={"command": sub, "args": payload, "args_text": rest},
                llm=False,
            )
        if command == "/save": return rd(intent="save", route="system", cmd="system.save", args={"name": arg or DEFAULT_SESSION_NAME})
        if command == "/load": return rd(intent="load", route="system", cmd="system.load", args={"name": arg or DEFAULT_SESSION_NAME})
        if command in {"/quit", "/exit"}: return rd(intent="quit", route="system", cmd="system.quit")
        if command == "/stream_on": return rd(intent="streaming", route="system", cmd="system.set_streaming", args={"enabled": True})
        if command == "/stream_off": return rd(intent="streaming", route="system", cmd="system.set_streaming", args={"enabled": False})
        if command == "/raw_on": return rd(intent="raw_json", route="system", cmd="system.set_raw_json", args={"enabled": True})
        if command == "/raw_off": return rd(intent="raw_json", route="system", cmd="system.set_raw_json", args={"enabled": False})
        if command == "/raw" and arg.lower() == "on": return rd(intent="raw_json", route="system", cmd="system.set_raw_json", args={"enabled": True})
        if command == "/raw" and arg.lower() == "off": return rd(intent="raw_json", route="system", cmd="system.set_raw_json", args={"enabled": False})
        if command == "/guard": return rd(intent="guard", route="system", cmd="system.guard")
        if command == "/patch": return rd(intent="patch_frontdoor", route="system", cmd="system.patch", args={"command": text})
        if command == "/remember":
            title, sep, body = arg.partition("::")
            if sep:
                return rd(intent="memory_remember", route="memory", cmd="memory.remember", args={"title": clean_text(title), "text": body.strip(), "tags": ["manual"]})
            return rd(intent="memory_remember", route="memory", cmd="memory.remember", args={"title": clean_text(arg)[:80] or "note", "text": arg, "tags": ["manual"]})
        if command == "/memory": return rd(intent="memory_retrieve", route="memory", cmd="memory.retrieve", args={"query": arg, "k": MAX_MEMORY_RESULTS})
        if command == "/memory_list": return rd(intent="memory_list", route="memory", cmd="memory.list", args={"limit": 20})
        if command == "/memory_clear": return rd(intent="memory_clear", route="memory", cmd="memory.clear")
        if command == "/fs":
            sub, _, rest = arg.partition(" ")
            sub = sub.lower().strip()
            rest = rest.strip()
            if sub in {"pwd", "cwd"}: return rd(intent="fs_pwd", route="tool", cmd="fs.pwd", args={})
            if sub in {"ls", "list", "dir"}: return rd(intent="fs_ls", route="tool", cmd="fs.ls", args={"path": rest or "."})
            if sub in {"read", "cat", "show", "open"}: return rd(intent="fs_read", route="tool", cmd="fs.read", args={"path": rest})
            return rd(intent="fs_ls", route="tool", cmd="fs.ls", args={"path": arg or "."})
        if command in {"/python", "/py"}: return rd(intent="python_run", route="tool", cmd="python.run", args={"code": arg})
        if command in {"/shell", "/bash"}: return rd(intent="shell_run", route="tool", cmd="shell.run", args={"command": arg})
        if command in {"/tool", "/tools"}:
            sub, _, rest = arg.partition(" ")
            sub_clean = clean_text(sub).lower()
            rest = rest.strip()
            if not sub_clean or sub_clean in {"list", "ls"}:
                verbose = bool(re.search(r"(?:^|\s)(?:--verbose|-v|verbose|full|details?|detailed)(?:\s|$)", rest, re.I))
                return rd(intent="cli_list", route="tool", cmd="cli.list", args={"verbose": verbose})
            if sub_clean == "scan": return rd(intent="cli_scan", route="tool", cmd="cli.scan", args={"path": rest or "."})
            if sub_clean in {"show", "info", "manifest"}: return rd(intent="cli_show", route="tool", cmd="cli.show", args={"tool_id": rest})
            if sub_clean in {"help", "--help", "-h"}: return rd(intent="cli_help", route="tool", cmd="cli.help", args={"tool_id": rest})
            return rd(intent="cli_run", route="tool", cmd="cli.run", args={"tool_id": sub, "args_text": rest})
        if command == "/tool-scan": return rd(intent="cli_scan", route="tool", cmd="cli.scan", args={"path": arg or "."})
        if command == "/tool-help": return rd(intent="cli_help", route="tool", cmd="cli.help", args={"tool_id": arg})
        # active three-lane/support front doors restored after semantic-stack decommission
        if command == "/prompt":
            return rd(intent="prompt", route="chat", cmd="chat.raw_prompt", args={"message": arg}, llm=True)

        if command == "/ground":
            ground_query = clean_text(arg)
            if ground_query.lower().startswith("prompt "):
                ground_query = clean_text(ground_query[7:])
            if not ground_query:
                return rd(
                    intent="ground_usage",
                    route="system",
                    cmd="system.validation_error",
                    args={
                        "message": "/ground requires a factual question.",
                        "examples": ["/ground what is quantum computing?", "/ground who directed Pie 2018?"],
                    },
                )
            return rd(
                intent="grounded_reply",
                route="chat",
                cmd="chat.grounded_reply",
                args={"message": ground_query, "query": ground_query, "allow_web_fallback": True},
                llm=True,
            )

        if command == "/scrape":
            return rd(intent="scrape", route="scrape", cmd="scrape.extract", args={"url": arg})

        if command == "/web":
            sub, _, rest = arg.partition(" ")
            sub = sub.lower().strip()
            rest = rest.strip()
            if sub == "search": return rd(intent="web_search", route="web", cmd="web.search", args={"query": rest, "max_results": 5}, llm=False)
            if sub == "fetch": return rd(intent="web_fetch", route="web", cmd="web.fetch", args={"url": rest})
            if sub in {"links", "extract_links"}: return rd(intent="web_links", route="web", cmd="web.extract_links", args={"url": rest} if rest else {})
            if sub == "follow":
                if not rest.strip():
                    return rd(intent="web_follow", route="web", cmd="web.follow_link", args={})
                return rd(intent="web_follow", route="web", cmd="web.follow_link", args={"link_index": coerce_int(rest, 0, 0, MAX_LINKS_PER_PAGE)})
            if sub == "summarize": return rd(intent="web_summarize", route="web", cmd="web.summarize", args={"url": rest} if rest else {}, llm=False)
            if sub in {"searchsum", "search_summarize", "search_and_summarize"}: return rd(intent="web_search_and_summarize", route="web", cmd="web.search_and_summarize", args={"query": rest, "max_results": 5}, llm=False)
            return rd(intent="web_search", route="web", cmd="web.search", args={"query": arg, "max_results": 5}, llm=False)
        return None

    def route(self, user_text: str, context: Dict[str, Any]) -> RouteDecision:
        user_text = str(user_text or "").strip()
        slash = self.try_parse_slash_command(user_text)
        if slash:
            return slash
        if user_text.startswith("/"):
            command = user_text.split(None, 1)[0]
            return RouteDecision(
                intent="validation_error",
                route="system",
                confidence=1.0,
                command="system.validation_error",
                args={
                    "message": f"Unknown slash command: {command}",
                "examples": ["/prompt write a plan", "/ground what is quantum computing?", "/summon prompt hello"],
            },
                requires_web=False,
                requires_memory=False,
                requires_llm_response=False,
                rewritten_user_request=user_text,
                reasoning_summary="Unknown slash command.",
            )
        return RouteDecision(
            intent="validation_error",
            route="system",
            confidence=1.0,
            command="system.validation_error",
            args={
                "message": "Plain text input is not sent to the LLM. Use /prompt for direct LLM, /ground for grounded/RAG answers, or /summon prompt for persona-routed prompting.",
                "examples": ["/prompt write a plan", "/ground what is quantum computing?", "/summon prompt hello"],
            },
            requires_llm_response=False,
            rewritten_user_request=user_text,
            reasoning_summary="Plain text input requires an explicit slash lane.",
        )


# ============================================================
# PLANNER / DISPATCHER
# ============================================================

class SharedPlanner:
    def __init__(self, registry: CommandRegistry) -> None:
        self.registry = registry

    def validation_error_plan(self, user_text: str, message: str, command: str = "", examples: Optional[List[str]] = None, source_kind: str = "tui") -> SharedPlan:
        return SharedPlan(
            route="system",
            command="system.validation_error",
            user_text=user_text,
            rewritten_text=user_text,
            args={"message": message, "command": command, "examples": examples or []},
            requires_llm_response=False,
            source_kind=source_kind,
            decision={},
        )

    def _arg_text(self, args: Dict[str, Any], *names: str) -> str:
        for name in names:
            value = args.get(name)
            if value is not None and str(value).strip():
                return clean_text(value)
        return ""

    def validate_plan_args(self, plan: SharedPlan) -> Optional[Dict[str, Any]]:
        cmd = plan.command
        args = plan.args or {}

        def err(message: str, examples: Optional[List[str]] = None) -> Dict[str, Any]:
            return {"message": message, "command": cmd, "examples": examples or []}

        if cmd == "web.search" and not self._arg_text(args, "query"):
            return err("web.search requires a query.", ["/web search pyTermTk docs"])
        if cmd == "web.fetch":
            url = self._arg_text(args, "url")
            if not is_probably_url(url):
                return err("web.fetch requires a valid URL.", ["/web fetch https://example.com"])
        if cmd == "scrape.extract":
            url = self._arg_text(args, "url")
            if not is_probably_url(url):
                return err("scrape.extract requires a valid URL.", ["/scrape https://example.com"])
        if cmd == "web.follow_link":
            try:
                int(args.get("link_index"))
            except Exception:
                return err("web.follow_link requires a numeric link index.", ["/web follow 0"])
        if cmd == "web.search_and_summarize" and not self._arg_text(args, "query"):
            return err("web.search_and_summarize requires a query.", ["/web searchsum pyTermTk Python TUI"])
        if cmd == "memory.remember" and not self._arg_text(args, "text", "note"):
            return err("memory.remember requires note text.", ["/remember title :: note text"])
        if cmd == "memory.retrieve" and not self._arg_text(args, "query"):
            return err("memory.retrieve requires a query.", ["/memory routing"])
        if cmd == "chat.raw_prompt" and not self._arg_text(args, "message"):
            return err("chat.raw_prompt requires a message.", ["/prompt write a plan"])
        if cmd == "chat.summon_prompt" and not self._arg_text(args, "message"):
            return err("chat.summon_prompt requires a message.", ["/summon prompt answer as the active persona"])
        if cmd == "chat.grounded_reply" and not self._arg_text(args, "message", "query") and not clean_text(plan.rewritten_text):
            return err("chat.grounded_reply requires a factual question.", ["/ground who directed Pie 2018?"])
        if cmd == "fs.read" and not self._arg_text(args, "path"):
            return err("fs.read requires a path.", ["/fs read tests.sh"])
        if cmd == "python.run" and not self._arg_text(args, "code"):
            return err("python.run requires code.", ["/python print('hello')"])
        if cmd == "shell.run":
            command_text = self._arg_text(args, "command")
            if not command_text:
                return err("shell.run requires a command.", ["/shell pwd", "/shell ls -la"])
            try:
                validate_shell_segments(split_shell_segments(command_text))
            except RuntimeError as exc:
                return err(str(exc), ["/shell pwd", "/shell ls -la"])
        if cmd == "cli.pipeline" and not self._arg_text(args, "sink"):
            return err("cli.pipeline requires a sink.", ["create comic prompt send to a1111", "write a conan story"])
        if cmd == "cli.pipeline":
            pipeline_source = clean_text(args.get("source") or "tool")
            if pipeline_source == "direct_text" and not self._arg_text(args, "source_text"):
                return err("cli.pipeline direct_text requires source_text.", ["render image of vintage horror vampire"])
            if pipeline_source not in {"last_cli_stdout", "direct_text"} and not self._arg_text(args, "source_tool_id"):
                return err("cli.pipeline requires a source tool, direct_text, or last_cli_stdout.", ["create comic prompt send to a1111", "render image of vintage horror vampire", "render last with a1111"])
            if clean_text(args.get("sink") or "").lower() == "llm":
                return err(
                    "cli.pipeline sink llm is disabled; use /prompt for direct model work or /ground for grounded answers.",
                    ["/prompt write a plan", "/ground what is quantum computing?", "/summon prompt hello"],
                )
        if cmd == "agent.explain_plan" and not self._arg_text(args, "request"):
            return err("agent.explain_plan requires a request.", ["/ground what is quantum computing?"])
        if cmd == "system.route" and not self._arg_text(args, "args_text"):
            return err(
                "system.route requires an inspect or dry-run action.",
                ["/route inspect what is the capital of France?", "/route dry-run what is the capital of France?"],
            )
        if cmd == "system.llm" and args.get("args_text") is None:
            args["args_text"] = "status"
        if cmd == "system.switch" and args.get("args_text") is None:
            args["args_text"] = "status"
        if cmd == "plugin.run" and not self._arg_text(args, "command"):
            return err("plugin.run requires a plugin command name.", ["/plugin example.echo hello"])
        return None

    def plan(self, decision: RouteDecision, user_text: str, source_kind: str = "tui") -> SharedPlan:
        command = decision.command if decision.command in self.registry.commands else "system.validation_error"
        route = self.registry.route_for(command)
        plan = SharedPlan(
            route=route,
            command=command,
            user_text=user_text,
            rewritten_text=decision.rewritten_user_request or user_text,
            args=dict(decision.args or {}),
            requires_llm_response=decision.requires_llm_response,
            source_kind=source_kind,
            decision=decision.to_dict(),
        )
        validation = self.validate_plan_args(plan)
        if validation:
            return self.validation_error_plan(
                user_text=user_text,
                message=validation.get("message", "Invalid command arguments."),
                command=validation.get("command", command),
                examples=validation.get("examples") if isinstance(validation.get("examples"), list) else [],
                source_kind=source_kind,
            )
        return plan


class SharedDispatcher:
    def __init__(self, app: "AgentCore") -> None:
        self.app = app

    def dispatch(self, plan: SharedPlan) -> DispatchResult:
        self.app.registry["last_plan"] = plan.to_dict()
        self.app.emit("plan", {"plan": plan.to_dict()})
        if plan.command.startswith("system."): return self.dispatch_system(plan)
        if plan.command.startswith("memory."): return self.dispatch_memory(plan)
        if plan.command.startswith("web."): return self.dispatch_web(plan)
        if plan.command.startswith("scrape."): return self.dispatch_scrape(plan)
        if plan.command.startswith("fs.") or plan.command.startswith("python.") or plan.command.startswith("shell.") or plan.command.startswith("cli."): return self.dispatch_tool(plan)
        if plan.command.startswith("plugin."): return self.dispatch_plugin(plan)
        if plan.command.startswith("agent."): return self.dispatch_agent(plan)
        if plan.command == "chat.contextual_reply": return self.dispatch_contextual_chat(plan)
        if plan.command == "chat.grounded_reply": return self.dispatch_grounded_chat(plan)
        if plan.command == "chat.summon_prompt": return self.dispatch_summon_prompt(plan)
        if plan.command == "chat.raw_prompt": return self.dispatch_raw_prompt(plan)
        if plan.command in {"chat.reply", "chat.prompt"}: return self.dispatch_chat(plan)
        return DispatchResult(ok=False, handled=False, message=f"Unknown command: {plan.command}")

    def dispatch_system(self, plan: SharedPlan) -> DispatchResult:
        cmd, args = plan.command, plan.args
        if cmd == "system.validation_error":
            message = clean_text(args.get("message") or "Invalid command arguments.")
            examples = args.get("examples") if isinstance(args.get("examples"), list) else []
            text = message
            if examples:
                text += "\n\nExamples:\n" + "\n".join(f"  {x}" for x in examples)
            self.app.emit_text("error", text)
            return DispatchResult(False, True, "validation_error", args)
        if cmd == "system.help":
            self.app.emit_text("system", self.app.commands.readable_help())
            return DispatchResult(True, True, "help")
        if cmd == "system.commands":
            text = as_json_text(self.app.commands.commands) if self.app.registry.get("raw_tool_json_enabled", False) else self.app.commands.readable_help()
            self.app.emit_text("system", text)
            return DispatchResult(True, True, "commands")
        if cmd == "system.patch":
            expression = clean_text(args.get("command") or plan.rewritten_text)
            try:
                result = run_patch_command(expression)
            except PatchFrontdoorError as exc:
                message = str(exc) + "\n\n" + patch_help_text()
                self.app.emit_text("system", message)
                return DispatchResult(False, True, "patch_error", {"error": str(exc)})

            lines = [
                "Patch command:",
                "  " + " ".join(result.command),
                f"Exit: {result.returncode}",
            ]

            if result.stdout.strip():
                lines.extend(["", "STDOUT:", result.stdout.rstrip()])

            if result.stderr.strip():
                lines.extend(["", "STDERR:", result.stderr.rstrip()])

            self.app.emit_text("system", "\n".join(lines))
            return DispatchResult(
                result.ok,
                True,
                "patch",
                {"command": result.command, "stdout": result.stdout, "stderr": result.stderr},
            )
        if cmd == "system.route":
            route_text = clean_text(args.get("args_text") or plan.rewritten_text)
            if not route_text:
                self.app.emit_text("system", "usage: legacy route inspection is unwired")
                return DispatchResult(False, True, "semantic_route_dry_run", {"error": "missing route input"})

            from core.batch_runner import run_command

            raise RuntimeError("legacy semantic route inspection is unwired.")
            if result.stdout:
                self.app.emit_text("route", result.stdout)
            elif result.stderr:
                self.app.emit_text("route", result.stderr)
            return DispatchResult(
                result.ok,
                True,
                result.mode,
                {"batch_result": result.to_dict()},
            )
        if cmd == "system.state":
            state = self.app.public_state()
            self.app.emit_text("state", self.app.format_public_state(state))
            return DispatchResult(True, True, "state", state)
        if cmd == "system.save":
            path = self.app.save_session(clean_text(args.get("name") or DEFAULT_SESSION_NAME))
            self.app.emit_text("system", f"Saved session to {path}")
            return DispatchResult(True, True, "saved", {"path": str(path)})
        if cmd == "system.load":
            path = self.app.load_session(clean_text(args.get("name") or DEFAULT_SESSION_NAME))
            self.app.emit_text("system", f"Loaded session from {path}")
            return DispatchResult(True, True, "loaded", {"path": str(path)})
        if cmd == "system.quit":
            self.app.emit("quit", {})
            return DispatchResult(True, True, "quit", {"quit": True})
        if cmd == "system.set_streaming":
            enabled = bool(args.get("enabled"))
            self.app.registry["streaming_enabled"] = enabled
            self.app.emit_text("system", f"Streaming {'enabled' if enabled else 'disabled'}.")
            return DispatchResult(True, True, "streaming", {"streaming_enabled": enabled})
        if cmd == "system.set_raw_json":
            enabled = bool(args.get("enabled"))
            self.app.registry["raw_tool_json_enabled"] = enabled
            self.app.emit_text("system", f"Raw JSON output {'enabled' if enabled else 'disabled'}.")
            return DispatchResult(True, True, "raw_json", {"raw_tool_json_enabled": enabled})
        if cmd == "system.clear_tui":
            self.app.emit("clear_output", {})
            return DispatchResult(True, True, "clear_tui")
        if cmd == "system.guard":
            self.app.emit_text("guard", self.app.format_output_guard_status())
            return DispatchResult(True, True, "guard", {"guard": self.app.output_guard_settings(), "last_output_guard": self.app.registry.get("last_output_guard")})
        if cmd == "system.sources":
            self.app.emit_text("sources", self.app.format_last_sources())
            return DispatchResult(True, True, "sources")
        if cmd == "system.grounding":
            self.app.emit_text("grounding", self.app.format_last_grounding())
            return DispatchResult(True, True, "grounding")
        if cmd == "system.last":
            self.app.emit_text("system", self.app.format_last_compact())
            return DispatchResult(True, True, "last")
        if cmd == "system.plan_last":
            self.app.emit_text("plan", self.app.format_last_plan())
            return DispatchResult(True, True, "plan_last")
        if cmd == "system.llm":
            args_text = clean_text(args.get("args_text") or "status")
            if is_llm_help_command(args_text):
                self.app.emit_text("system", llm_help_text())
                return DispatchResult(True, True, "llm_help", {"commands": "switch_backed_llm_front_door"})

            if not is_llm_config_command(args_text):
                command_text = "/llm" if args_text == "status" else f"/llm {args_text}"
                result = resolve_llm_front_door(
                    command_text,
                    allow_provider_calls=bool(self.app.registry.get("llm_provider_calls_enabled", False)),
                    allow_chat_execution=bool(self.app.registry.get("llm_chat_execution_enabled", True)),
                )
                payload = result.to_dict()
                self.app.emit_text("system", format_llm_front_door_result(result))
                return DispatchResult(
                    bool(result.plan_allowed),
                    True,
                    "llm_front_door",
                    payload,
                )

            current_raw = self.app.registry.get("llm_config")
            try:
                config_args_text = llm_config_args(args_text)
                if isinstance(current_raw, dict):
                    current = LLMConfig.from_dict(current_raw)
                elif isinstance(current_raw, LLMConfig):
                    current = current_raw
                else:
                    current = default_llm_config()

                applied = apply_llm_command(current, config_args_text)
                if applied is None:
                    raise LLMConfigError(f"unknown /llm config command: {config_args_text}")
                new_config, message = applied
                self.app.registry["llm_config"] = new_config.to_dict()
                self.app.emit_text("system", message)
                return DispatchResult(True, True, "llm_config", new_config.to_dict())
            except LLMConfigError as exc:
                message = f"LLM config error: {exc}"
                self.app.emit_text("system", message)
                return DispatchResult(False, True, "llm_config_error", {"error": str(exc)})
        if cmd == "system.switch":
            args_text = clean_text(args.get("args_text") or "status")
            tokens = args_text.split() if args_text else ["status"]
            if not tokens:
                tokens = ["status"]

            if tokens[0] == "profile":
                profile_tokens = tokens[1:] or ["status"]
                allowed_profile_commands = {"status", "list", "show", "validate", "plan-apply"}
                blocked_profile_tokens = {
                    "apply", "set", "use", "activate", "enable", "disable",
                    "on", "off", "write", "delete",
                }

                profile_first = profile_tokens[0]
                if profile_first not in allowed_profile_commands:
                    message = (
                        "Switch profile error: unsupported /switch profile command. "
                        "Allowed: status, list, show, validate, plan-apply."
                    )
                    self.app.emit_text("system", message)
                    return DispatchResult(False, True, "switch_profile_error", {"error": message})

                if any(token in blocked_profile_tokens for token in profile_tokens):
                    message = "Switch profile error: apply/use/set/runtime mutation is not exposed by /switch profile."
                    self.app.emit_text("system", message)
                    return DispatchResult(False, True, "switch_profile_error", {"error": message})

                proc = __import__("subprocess").run(
                    [__import__("sys").executable, "external CLI payloads/switch_profiles_tool.py", *profile_tokens],
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=30,
                )
                output = (proc.stdout or "").strip()
                if proc.stderr:
                    output = (output + "\n" if output else "") + "stderr:\n" + proc.stderr.strip()
                self.app.emit_text("system", output or f"switch.profiles exited with {proc.returncode}")
                return DispatchResult(
                    proc.returncode == 0,
                    True,
                    "switch_profiles",
                    {"returncode": proc.returncode, "args": profile_tokens},
                )

            allowed_commands = {"status", "list", "show", "plan", "read", "apply-gate"}
            blocked_tokens = {
                "apply", "rollback", "sudo", "write", "restart", "enable",
                "disable", "install", "remove", "delete",
            }

            first = tokens[0]
            if first not in allowed_commands:
                message = (
                    "Switch matrix error: unsupported /switch command. "
                    "Allowed: status, list, show, plan, read, apply-gate."
                )
                self.app.emit_text("system", message)
                return DispatchResult(False, True, "switch_matrix_error", {"error": message})

            if any(token in blocked_tokens for token in tokens):
                message = "Switch matrix error: apply/rollback/sudo/write operations are not exposed by /switch."
                self.app.emit_text("system", message)
                return DispatchResult(False, True, "switch_matrix_error", {"error": message})

            if first == "read" and "--dry-run" not in tokens:
                tokens.append("--dry-run")

            proc = __import__("subprocess").run(
                [__import__("sys").executable, "external CLI payloads/switch_matrix_tool.py", *tokens],
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
            output = (proc.stdout or "").strip()
            if proc.stderr:
                output = (output + "\n" if output else "") + "stderr:\n" + proc.stderr.strip()
            self.app.emit_text("system", output or f"switch.matrix exited with {proc.returncode}")
            return DispatchResult(proc.returncode == 0, True, "switch_matrix", {"returncode": proc.returncode, "args": tokens})
        if cmd == "system.last_json":
            self.app.emit_text("last_result_json", self.app.format_last_json())
            return DispatchResult(True, True, "last_json")
        if cmd == "system.config":
            self.app.emit_text("config", self.app.format_config_summary())
            return DispatchResult(True, True, "config")
        if cmd == "system.plugins":
            self.app.emit_text("plugins", self.app.format_plugins_list())
            return DispatchResult(True, True, "plugins")
        if cmd == "system.reload_plugins":
            report = self.app.load_plugins()
            if self.app.registry.get("raw_tool_json_enabled", False):
                text = "Reloaded plugins.\n\n" + as_json_text(report)
            else:
                text = (
                    f"Reloaded plugins. Loaded: {report.get('loaded_count', 0)} | "
                    f"Errors: {report.get('error_count', 0)}\n\n"
                    + self.app.format_plugins_list()
                )
            self.app.emit_text("plugins", text)
            return DispatchResult(True, True, "reload_plugins", report)
        if cmd == "system.switches":
            query = clean_text(args.get("query") or "")
            payload = self.app.switches_payload(query)
            self.app.emit_text("switches", self.app.format_switches_list(query))
            return DispatchResult(True, True, "switches", payload)
        if cmd == "system.switch":
            expression = str(args.get("expression") or "").strip()
            result = self.app.run_switch_expression(expression, source_kind=plan.source_kind)
            if self.app.registry.get("raw_tool_json_enabled", False):
                self.app.emit_json("switch", result)
            else:
                self.app.emit_text("switch", self.app.format_plugin_result(result))
            return DispatchResult(bool(result.get("ok")), bool(result.get("handled", True)), "switch", result)
        if cmd == "system.metadata":
            self.app.emit_text("metadata", self.app.format_metadata_summary())
            return DispatchResult(True, True, "metadata")
        if cmd == "system.identity":
            question = clean_text(args.get("question") or plan.user_text)
            self.app.emit_text("identity", self.app.format_identity_answer(question))
            return DispatchResult(True, True, "identity")
        if cmd == "system.prompts":
            self.app.emit_text("prompts", self.app.format_prompts_summary())
            return DispatchResult(True, True, "prompts")
        if cmd == "system.reload_config":
            bundle = self.app.reload_config()
            self.app.emit_text("config", "Reloaded external config files.\n\n" + self.app.format_config_summary())
            return DispatchResult(True, True, "reload_config", {"config": bundle})
        if cmd == "system.personality":
            self.app.emit_text("personality", self.app.format_personality_summary())
            return DispatchResult(True, True, "personality")
        if cmd == "system.personalities":
            self.app.emit_text("personalities", self.app.format_personalities_list())
            return DispatchResult(True, True, "personalities")
        if cmd == "system.set_personality":
            name = clean_text(args.get("name") or "")
            selected = self.app.set_active_personality(name)
            self.app.emit_text(
                "personality",
                f"Active behavior preset set to: {selected}\n\n" + self.app.format_personality_summary(),
            )
            return DispatchResult(True, True, "set_personality", {"active_personality": selected})
        if cmd == "system.summon":
            payload_text = str(args.get("payload") or "").strip()
            if not payload_text:
                raise RuntimeError("/summon requires a persona prompt or JSON payload.")
            payload = parse_summon_payload(payload_text)
            self.app.set_active_summon(payload)
            self.app.emit_text("summon", self.app.format_summon_status())
            return DispatchResult(True, True, "summon", {"summon": payload})
        if cmd == "system.unsummon":
            previous = self.app.clear_active_summon()
            self.app.emit_text("summon", "Summon cleared. Returned to active personality.")
            return DispatchResult(True, True, "unsummon", {"previous": previous})
        if cmd == "system.summon_status":
            self.app.emit_text("summon", self.app.format_summon_status())
            return DispatchResult(True, True, "summon_status")
        return DispatchResult(False, False, f"Unhandled system command: {cmd}")

    def dispatch_memory(self, plan: SharedPlan) -> DispatchResult:
        cmd, args = plan.command, plan.args
        if cmd == "memory.remember":
            item = self.app.memory.remember(
                clean_text(args.get("title") or "note"),
                str(args.get("text") or args.get("note") or plan.rewritten_text or ""),
                args.get("tags") if isinstance(args.get("tags"), list) else ["note"],
            )
            self.app.emit("memory", {"message": f"Remembered: {item['title']}", "item": item})
            return DispatchResult(True, True, "memory_remember", {"item": item})

        if cmd == "memory.retrieve":
            query = clean_text(args.get("query") or plan.rewritten_text)
            results = self.app.memory.retrieve(query, coerce_int(args.get("k"), MAX_MEMORY_RESULTS, 1, 50))
            if not results:
                self.app.emit("memory", {"message": f"No memory results found for: {query}", "query": query, "results": []})
                return DispatchResult(True, True, "memory_retrieve", {"query": query, "results": []})
            if self.app.registry.get("raw_tool_json_enabled", False):
                self.app.emit_json("memory", {"query": query, "results": results})
                return DispatchResult(True, True, "memory_retrieve", {"query": query, "results": results})
            tool_context = (
                f"USER TASK:\n{plan.user_text}\n\n"
                f"MEMORY QUERY USED:\n{query}\n\n"
                "ANSWERING RULE:\n"
                "Answer the USER TASK directly. The memory results below are evidence, not the final answer. "
                "Do not merely summarize the memory list.\n\n"
                f"{format_memory_results_for_context(query, results)}"
            )
            response = self.app.synthesize_tool_response(
                user_text=plan.user_text,
                tool_name="memory.retrieve",
                tool_context=tool_context,
                instruction=(
                    "Answer the user's original request directly using the memory results as evidence. "
                    "Do not merely summarize the memory list. "
                    "Mention the most relevant remembered facts first. "
                    "If the memories only partially answer the request, say what is missing."
                ),
            )
            return DispatchResult(True, True, "memory_retrieve", {"query": query, "results": results, "response": response})

        if cmd == "memory.list":
            results = self.app.memory.list_recent(coerce_int(args.get("limit"), 20, 1, 200))
            if not results:
                self.app.emit_text("memory", "No memory notes saved.")
            else:
                lines = ["Recent memory notes:"]
                for item in results:
                    lines.append(f"- {item.get('title')} [{item.get('created_at')}]\n  {truncate_text(clean_text(item.get('text', '')), 240)}")
                self.app.emit_text("memory", "\n".join(lines))
            return DispatchResult(True, True, "memory_list", {"memory": results})

        if cmd == "memory.clear":
            data = self.app.memory.clear()
            self.app.emit_text("memory", f"Cleared {data['cleared']} notes.")
            return DispatchResult(True, True, "memory_clear", data)

        return DispatchResult(False, False, f"Unhandled memory command: {cmd}")

    def dispatch_tool(self, plan: SharedPlan) -> DispatchResult:
        cmd, args = plan.command, plan.args or {}
        root = tool_root()

        if cmd == "fs.pwd":
            text = str(root)
            self.app.emit_text("tool", text)
            return DispatchResult(True, True, "fs_pwd", {"cwd": text})

        if cmd == "fs.ls":
            path = resolve_safe_tool_path(args.get("path") or ".")
            if not path.exists():
                raise RuntimeError(f"Path does not exist: {path}")
            if not path.is_dir():
                raise RuntimeError(f"Path is not a directory: {path}")
            entries = []
            for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:200]:
                try:
                    stat = child.stat()
                    rel = child.relative_to(root) if child != root else Path(".")
                    entries.append({
                        "name": child.name + ("/" if child.is_dir() else ""),
                        "path": str(rel),
                        "type": "dir" if child.is_dir() else "file",
                        "size": stat.st_size,
                    })
                except OSError:
                    entries.append({"name": child.name, "path": child.name, "type": "unknown", "size": None})
            lines = [f"Listing: {path.relative_to(root) if path != root else Path('.')}" ]
            if not entries:
                lines.append("(empty)")
            else:
                for item in entries:
                    size = "" if item["type"] == "dir" else f"  {item.get('size', 0)} bytes"
                    lines.append(f"{item['name']}{size}")
            out = "\n".join(lines)
            self.app.emit_text("tool", out)
            return DispatchResult(True, True, "fs_ls", {"path": str(path), "entries": entries})

        if cmd == "fs.read":
            path = resolve_safe_tool_path(args.get("path") or "")
            if not path.exists():
                raise RuntimeError(f"File does not exist: {path}")
            if not path.is_file():
                raise RuntimeError(f"Path is not a file: {path}")
            if path.suffix.lower() not in TEXT_FILE_SUFFIX_ALLOWLIST:
                raise RuntimeError(f"Refusing to read unsupported file type: {path.suffix or '(no suffix)'}")
            size = path.stat().st_size
            if size > TOOL_READ_MAX_BYTES:
                raise RuntimeError(f"File is too large to read safely ({size} bytes > {TOOL_READ_MAX_BYTES}).")
            text = path.read_text(encoding="utf-8", errors="replace")
            rel = str(path.relative_to(root))
            out = f"File: {rel}\nSize: {size} bytes\n\n{truncate_text(text, TOOL_READ_MAX_BYTES)}"
            self.app.emit_text("tool", out)
            return DispatchResult(True, True, "fs_read", {"path": rel, "size": size, "text": text})

        if cmd == "python.run":
            code = extract_python_code_from_text(args.get("code") or plan.rewritten_text)
            if not code.strip():
                raise RuntimeError("python.run requires code.")
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as handle:
                handle.write(code)
                temp_path = handle.name
            try:
                proc = subprocess.run(
                    [sys.executable, temp_path],
                    cwd=str(root),
                    text=True,
                    capture_output=True,
                    timeout=TOOL_RUN_TIMEOUT_SECONDS,
                    check=False,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f"python.run timed out after {TOOL_RUN_TIMEOUT_SECONDS} seconds.") from exc
            finally:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
            out = "Python code:\n" + code.strip() + "\n\n" + format_tool_completed_process([sys.executable, "<tempfile>.py"], proc)
            self.app.emit_text("tool", out)
            return DispatchResult(True, True, "python_run", {"code": code, "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr})

        if cmd == "shell.run":
            command_text = extract_shell_command_from_text(args.get("command") or plan.rewritten_text)
            segments = split_shell_segments(command_text)
            validate_shell_segments(segments)
            outputs = []
            payload = []
            for seg in segments:
                try:
                    proc = subprocess.run(
                        seg,
                        cwd=str(root),
                        text=True,
                        capture_output=True,
                        timeout=TOOL_RUN_TIMEOUT_SECONDS,
                        check=False,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise RuntimeError(f"shell.run timed out after {TOOL_RUN_TIMEOUT_SECONDS} seconds while running: {' '.join(seg)}") from exc
                outputs.append(format_tool_completed_process(seg, proc))
                payload.append({"args": seg, "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr})
                if proc.returncode != 0:
                    break
            out = "\n\n".join(outputs)
            self.app.emit_text("tool", out)
            return DispatchResult(True, True, "shell_run", {"command": command_text, "runs": payload})

        if cmd == "cli.list":
            self.app.load_cli_tools()
            tools = self.app.cli_tools.list_tools()
            verbose = bool(args.get("verbose", False))
            self.app.emit_text("tool", self.app.format_cli_tools_list(verbose=verbose))
            return DispatchResult(True, True, "cli_list", {"tools": tools, "verbose": verbose})

        if cmd == "cli.scan":
            scan_path = str(args.get("path") or ".").strip()
            payload = self.app.cli_tools.scan_path(scan_path, write=True)
            self.app.registry["cli_tool_load_report"] = {
                "loaded_count": payload.get("loaded_count", 0),
                "error_count": len(self.app.cli_tools.errors),
                "errors": list(self.app.cli_tools.errors),
            }
            lines = [
                f"Scanned: {payload.get('scanned_path')}",
                f"Draft manifests created: {payload.get('created_count')}",
                f"Skipped: {payload.get('skipped_count')}",
                f"Loaded CLI bridge tools: {payload.get('loaded_count')}",
            ]
            for item in (payload.get("created") or [])[:40]:
                lines.append(f"- {item.get('tool_id')} -> {item.get('path')}")
            if payload.get("created_count", 0) > 40:
                lines.append("...")
            self.app.emit_text("tool", "\n".join(lines))
            return DispatchResult(True, True, "cli_scan", payload)

        if cmd == "cli.show":
            tool_id = clean_text(args.get("tool_id") or "")
            self.app.emit_text("tool", self.app.format_cli_tool_manifest(tool_id))
            rec = self.app.cli_tools.get_tool(tool_id)
            return DispatchResult(bool(rec), True, "cli_show", {"tool": rec.to_dict() if rec else None})

        if cmd == "cli.help":
            tool_id = clean_text(args.get("tool_id") or "")
            result = self.app.cli_tools.help_tool(tool_id)
            result = normalize_plugin_result(result if isinstance(result, dict) else {})
            self.app.emit_text("tool", self.app.format_plugin_result(result))
            return DispatchResult(bool(result.get("ok")), bool(result.get("handled", True)), "cli_help", result)

        if cmd == "cli.run":
            tool_id = clean_text(args.get("tool_id") or "")
            args_text = str(args.get("args_text") or "").strip()
            result = self.app.cli_tools.run_tool(tool_id, arg_text=args_text)
            result = normalize_plugin_result(result if isinstance(result, dict) else {})
            self.app.registry["last_cli_tool_result"] = result
            try:
                stdout = self.app.last_cli_stdout()
                if stdout:
                    self.app.write_pipeline_text_file("last_tool_stdout.txt", stdout)
            except Exception:
                pass
            if self.app.registry.get("raw_tool_json_enabled", False):
                self.app.emit_json("tool", result)
            else:
                self.app.emit_text("tool", self.app.format_plugin_result(result))
            return DispatchResult(bool(result.get("ok")), bool(result.get("handled", True)), "cli_run", result)

        if cmd == "cli.pipeline":
            source = clean_text(args.get("source") or "tool") or "tool"
            source_tool_id = clean_text(args.get("source_tool_id") or "")
            source_args_text = str(args.get("source_args_text") or "").strip()
            sink = clean_text(args.get("sink") or "").lower()
            sink_args = args.get("sink_args") if isinstance(args.get("sink_args"), dict) else {}

            if source == "direct_text":
                source_stdout = str(args.get("source_text") or "").strip()
                if not source_stdout:
                    raise RuntimeError("No direct text prompt is available to pipeline.")
            elif source == "last_cli_stdout":
                source_stdout = self.app.last_cli_stdout()
                if not source_stdout:
                    raise RuntimeError("No previous CLI tool stdout is available to pipeline.")
            else:
                source_result_raw = self.app.cli_tools.run_tool(source_tool_id, arg_text=source_args_text)
                source_result = normalize_plugin_result(source_result_raw if isinstance(source_result_raw, dict) else {})
                self.app.registry["last_cli_tool_result"] = source_result
                if not source_result.get("ok"):
                    self.app.emit_text("tool", self.app.format_plugin_result(source_result))
                    return DispatchResult(False, True, "cli_pipeline_source_failed", source_result)
                source_stdout = str((source_result.get("data") or {}).get("stdout") or "").strip()
                if not source_stdout:
                    source_stdout = str((source_result.get("display") or {}).get("text") or "").strip()
                if not source_stdout:
                    raise RuntimeError(f"Pipeline source produced no stdout: {source_tool_id}")

            if sink == "a1111":
                prompt_bundle = self.app.extract_pipeline_prompt_bundle(source_stdout)
                prompt_path = self.app.write_pipeline_prompt_file(prompt_bundle.get("prompt", source_stdout))
                negative_path = ""
                if prompt_bundle.get("negative_prompt"):
                    negative_path = self.app.write_pipeline_negative_file(prompt_bundle.get("negative_prompt", ""))
                sink_parts = ["txt2img", "--prompt-file", prompt_path]
                if negative_path:
                    sink_parts += ["--negative-file", negative_path]
                if bool(sink_args.get("dry_run")):
                    sink_parts += ["--dry-run", "true"]
                if bool(sink_args.get("open")):
                    sink_parts += ["--open", "true"]
                for flag in ["steps", "width", "height"]:
                    if flag in sink_args:
                        sink_parts += ["--" + flag.replace("_", "-"), str(sink_args[flag])]
                sink_text = " ".join(shlex.quote(x) for x in sink_parts)
                result = self.app.cli_tools.run_tool(A1111_PIPELINE_TOOL_ID, arg_text=sink_text)
                result = normalize_plugin_result(result if isinstance(result, dict) else {})
                result.setdefault("data", {})
                if isinstance(result.get("data"), dict):
                    result["data"].setdefault("pipeline", {"source": source, "source_tool_id": source_tool_id, "sink": sink, "prompt_file": prompt_path, "negative_file": negative_path, "extracted_prompt": bool(prompt_bundle.get("extracted"))})
                self.app.registry["last_cli_tool_result"] = result
                self.app.emit_text("tool", self.app.format_plugin_result(result))
                return DispatchResult(bool(result.get("ok")), True, "cli_pipeline_a1111", result)

            if sink == "llm":
                message = (
                    "Pipeline sink llm is disabled; use /prompt for direct model work or /ground for grounded/RAG work."
                )
                self.app.emit_text("tool", message)
                return DispatchResult(False, True, "validation_error", {"message": message, "source": source, "source_tool_id": source_tool_id})

            raise RuntimeError(f"Unknown cli.pipeline sink: {sink}")

        return DispatchResult(False, False, f"Unhandled local tool command: {cmd}")

    def dispatch_web(self, plan: SharedPlan) -> DispatchResult:
        cmd, args = plan.command, plan.args
        allow_private = bool(self.app.registry.get("allow_private_url_fetch", False))

        if cmd == "web.search":
            source_hint = clean_text(args.get("source_hint") or "")
            query = normalize_search_query(args.get("query") or plan.rewritten_text, source_hint)
            max_results = coerce_int(args.get("max_results"), 5, 1, MAX_SEARCH_RESULTS)
            answer_profile = clean_text(args.get("answer_profile") or infer_search_answer_profile(plan.user_text, query))
            response_format = clean_text(args.get("format") or "")
            self.app.emit("web", {"message": f"Searching: {query}"})
            data = self.app.web.search(query, max_results)
            self.app.registry["last_web_search"] = data
            if self.app.registry.get("raw_tool_json_enabled", False):
                self.app.emit_json("web.search", data)
                return DispatchResult(True, True, "web_search", data)
            fact_hints = extract_search_fact_hints(data, answer_profile=answer_profile, source_hint=source_hint)
            structured_context = extract_search_structured_context(data)
            tool_context = (
                f"USER TASK:\n{plan.user_text}\n\n"
                f"SEARCH QUERY USED:\n{query}\n\n"
                f"SOURCE HINT:\n{source_hint or 'general'}\n\n"
                f"ANSWER PROFILE:\n{answer_profile}\n\n"
                f"RESPONSE FORMAT HINT:\n{response_format or 'none'}\n\n"
                "EXTRACTED FACT HINTS:\n"
                f"{fact_hints or 'No explicit fact hints extracted.'}\n\n"
                f"STRUCTURED CONTEXT:\n{as_json_text(structured_context)}\n\n"
                f"{format_search_results_for_context(data)}"
            )
            self.app.registry["last_search_task"] = plan.user_text
            self.app.registry["last_search_query"] = query
            self.app.registry["last_search_answer_profile"] = answer_profile
            self.app.registry["last_search_response_format"] = response_format
            self.app.registry["last_search_source_hint"] = source_hint
            self.app.registry["last_search_fact_hints"] = fact_hints
            self.app.registry["last_search_context"] = tool_context
            self.app.registry["last_search_structured"] = structured_context
            response = format_search_results_for_context(data)
            self.app.emit_text("web", response)
            return DispatchResult(True, True, "web_search", {"search": data, "response": response})

        if cmd == "web.fetch":
            url = clean_text(args.get("url") or plan.rewritten_text)
            self.app.emit("web", {"message": f"Fetching: {url}"})
            data = self.app.web.fetch(url, allow_private=allow_private)
            self.app.registry["last_web_page"] = data
            lines = [
                f"Fetched: {data.get('title') or '(untitled)'}",
                f"URL: {data.get('url')}",
                f"Status: {data.get('status_code')}",
                "",
                truncate_text(data.get("text_preview", ""), 1200),
            ]
            if data.get("links"):
                lines += ["", "Links:", readable_link_list(data.get("links") or [], 20)]
            self.app.emit_text("web", "\n".join(lines))
            return DispatchResult(True, True, "web_fetch", data)

        if cmd == "web.extract_links":
            url = clean_text(args.get("url") or "")
            if url:
                data = self.app.web.fetch(url, allow_private=allow_private)
                self.app.registry["last_web_page"] = data
            else:
                data = self.app.registry.get("last_web_page")
                if not isinstance(data, dict):
                    raise RuntimeError("No last web page. Use /web fetch <url> first.")
            links = data.get("links", [])
            self.app.emit_text(
                "web",
                f"Links from: {data.get('title') or data.get('url')}\n" + (readable_link_list(links, 50) if links else "No links found."),
            )
            return DispatchResult(True, True, "web_links", {"links": links})

        if cmd == "web.follow_link":
            page = self.app.registry.get("last_web_page")
            if not isinstance(page, dict):
                raise RuntimeError("No last web page. Use /web fetch <url> first.")
            links = page.get("links") or []
            if not links:
                raise RuntimeError("The last fetched page has no extracted links.")
            index = coerce_int(args.get("link_index"), 0, 0, max(0, len(links) - 1))
            if index >= len(links):
                raise RuntimeError(f"Link index out of range. Available: 0-{len(links) - 1}")
            target = links[index]["url"]
            self.app.emit("web", {"message": f"Following link {index}: {target}"})
            data = self.app.web.fetch(target, allow_private=allow_private)
            self.app.registry["last_web_page"] = data
            self.app.emit_text(
                "web",
                f"Fetched: {data.get('title') or '(untitled)'}\nURL: {data.get('url')}\n\n"
                f"{truncate_text(data.get('text_preview', ''), 1200)}\n\nLinks:\n"
                f"{readable_link_list(data.get('links') or [], 20)}",
            )
            return DispatchResult(True, True, "web_follow", data)

        if cmd == "web.summarize":
            url = clean_text(args.get("url") or "")
            if url:
                page = self.app.web.fetch(url, allow_private=allow_private)
                self.app.registry["last_web_page"] = page
            else:
                page = self.app.registry.get("last_web_page")
                if not isinstance(page, dict):
                    raise RuntimeError("No last web page. Use /web fetch <url> first.")
            summary = "\n".join(
                [
                    f"WEB summary:",
                    f"  url: {page.get('url') or ''}",
                    f"  title: {page.get('title') or ''}",
                    f"  status: {page.get('status_code') or ''}",
                    "",
                    _clip_text(page.get("text_preview") or page.get("text") or "", limit=4000),
                ]
            ).rstrip()
            payload = {"url": page.get("url"), "title": page.get("title"), "summary": summary}
            self.app.registry["last_web_summary"] = payload
            self.app.emit_text("web", summary)
            return DispatchResult(True, True, "web_summarize", payload)

        if cmd == "web.search_and_summarize":
            query = normalize_search_query(args.get("query") or plan.rewritten_text, clean_text(args.get("source_hint") or ""))
            max_results = coerce_int(args.get("max_results"), 5, 1, MAX_SEARCH_RESULTS)
            self.app.emit("web", {"message": f"Searching: {query}"})
            search_data = self.app.web.search(query, max_results)
            self.app.registry["last_web_search"] = search_data
            results = search_data.get("results") or []
            if not results:
                self.app.emit_text("web", "No search results found.")
                return DispatchResult(True, True, "web_search_and_summarize", {"query": query, "results": []})
            top = results[0]
            self.app.emit("web", {"message": f"Fetching top result: {top.get('title')} — {top.get('url')}"})
            page = self.app.web.fetch(top["url"], allow_private=allow_private)
            self.app.registry["last_web_page"] = page
            summary = "\n".join(
                [
                    f"WEB search and summarize:",
                    f"  query: {query}",
                    f"  top_title: {top.get('title') or ''}",
                    f"  top_url: {top.get('url') or ''}",
                    "",
                    _clip_text(page.get("text_preview") or page.get("text") or "", limit=3000),
                    "",
                    "Search results:",
                    format_search_results_for_context(search_data),
                ]
            ).rstrip()
            payload = {"query": query, "top_result": top, "summary": summary, "sources": results}
            self.app.registry["last_web_summary"] = payload
            self.app.emit_text("web", summary)
            return DispatchResult(True, True, "web_search_and_summarize", payload)

        return DispatchResult(False, False, f"Unhandled web command: {cmd}")

    def dispatch_scrape(self, plan: SharedPlan) -> DispatchResult:
        cmd, args = plan.command, plan.args
        if cmd != "scrape.extract":
            return DispatchResult(False, False, f"Unhandled scrape command: {cmd}")

        url = clean_text(args.get("url") or plan.rewritten_text)
        if not url:
            message = "scrape.extract requires a valid URL."
            self.app.emit_text("scrape", message)
            return DispatchResult(False, True, "scrape_error", {"error": message})

        allow_private = bool(self.app.registry.get("allow_private_url_fetch", False))
        self.app.emit("scrape", {"message": f"Scraping: {url}"})
        try:
            page = self.app.web.fetch(url, allow_private=allow_private)
        except Exception as exc:
            message = f"scrape.extract failed for {url}: {exc}"
            self.app.emit_text("scrape", message)
            return DispatchResult(False, True, "scrape_error", {"error": str(exc), "url": url})

        text = page.get("text_preview") or page.get("text") or ""
        lines = [
            "SCRAPE extract:",
            f"  url: {page.get('url') or url}",
            f"  final_url: {page.get('final_url') or page.get('url') or url}",
            f"  status: {page.get('status_code')}",
            f"  title: {page.get('title') or '(untitled)'}",
            "",
            _clip_text(text, limit=4000),
        ]
        links = page.get("links") or []
        if links:
            lines += ["", "Links:", readable_link_list(links, 20)]
        payload = {
            "url": page.get("url") or url,
            "final_url": page.get("final_url") or page.get("url") or url,
            "status_code": page.get("status_code"),
            "title": page.get("title") or "",
            "text": text,
            "links": links,
        }
        self.app.registry["last_scrape_page"] = payload
        self.app.emit_text("scrape", "\n".join(lines))
        return DispatchResult(True, True, "scrape_extract", payload)

    def dispatch_plugin(self, plan: SharedPlan) -> DispatchResult:
        cmd, args = plan.command, plan.args

        if cmd != "plugin.run":
            return DispatchResult(False, False, f"Unhandled plugin command: {cmd}")

        plugin_command = clean_text(args.get("command") or "")
        args_text = str(args.get("args_text") or "").strip()
        payload_args = args.get("args") if isinstance(args.get("args"), dict) else {}

        if args_text and not payload_args:
            payload_args = {
                "text": args_text,
                "message": args_text,
                "query": args_text,
            }

        result = self.app.plugins.dispatch(
            plugin_command,
            payload_args,
            self.app.plugin_context(user_text=plan.user_text, source_kind=plan.source_kind),
        )

        self.app.registry["last_plugin_result"] = result

        if self.app.registry.get("raw_tool_json_enabled", False):
            self.app.emit_json("plugin", result)
        else:
            self.app.emit_text("plugin", self.app.format_plugin_result(result))

        return DispatchResult(
            ok=bool(result.get("ok")),
            handled=bool(result.get("handled", True)),
            message=clean_text(result.get("message") or "plugin_result"),
            data={"plugin_result": result},
        )

    def dispatch_agent(self, plan: SharedPlan) -> DispatchResult:
        cmd, args = plan.command, plan.args
        if cmd == "agent.noop":
            self.app.emit_text("agent", "noop")
            return DispatchResult(True, True, "noop")
        if cmd == "agent.router_explain":
            self.app.emit_text("agent", format_agent_router_explanation())
            return DispatchResult(True, True, "agent_router_explain")

        if cmd == "agent.explain_plan":
            request = clean_text(args.get("request") or "")
            if not request:
                raise RuntimeError("legacy planning surface is unwired.")
            decision = self.app.router.route(request, self.app.router_context())
            nested_plan = self.app.planner.plan(decision, request, source_kind="plan_preview")
            data = {"decision": decision.to_dict(), "plan": nested_plan.to_dict()}
            if self.app.registry.get("raw_tool_json_enabled", False):
                self.app.emit_json("plan_preview", data)
            else:
                text = self.app.format_decision_summary(decision.to_dict()) + "\n\n" + self.app.format_plan_summary(nested_plan.to_dict())
                self.app.emit_text("plan", text)
            try:
                switch_validation_request = clean_text(args.get("request") or "")
                switch_validation = SwitchRouteValidator().validate_text(switch_validation_request)
                self.app.emit_text("plan", switch_validation.format_plan_block())
            except Exception as exc:
                self.app.emit_text(
                    "plan",
                    "Switch route validation:\n"
                    "- status: blocked\n"
                    f"- reason: validator error: {exc}",
                )

            return DispatchResult(True, True, "plan_preview", data)
        return DispatchResult(False, False, f"Unhandled agent command: {cmd}")

    def dispatch_contextual_chat(self, plan: SharedPlan) -> DispatchResult:
        message = clean_text(plan.args.get("message") or plan.rewritten_text or plan.user_text)
        reply = self.app.contextual_reply(message)
        return DispatchResult(True, True, "contextual_reply", {"reply": reply})

    def dispatch_summon_prompt(self, plan: SharedPlan) -> DispatchResult:
        message = clean_text(plan.args.get("message") or plan.rewritten_text or plan.user_text)
        if not self.app.has_active_summon():
            text = "/summon prompt requires an active summon. Use /summon <persona prompt or JSON> first."
            self.app.emit_text("error", text)
            return DispatchResult(False, True, "summon_prompt_requires_active_summon", {"message": text})
        reply = self.app.summon_prompt_reply(message)
        return DispatchResult(True, True, "summon_prompt_reply", {"reply": reply})

    def dispatch_raw_prompt(self, plan: SharedPlan) -> DispatchResult:
        message = clean_text(plan.args.get("message") or plan.rewritten_text or plan.user_text)
        reply = self.app.raw_prompt_reply(message)
        return DispatchResult(True, True, "raw_prompt_reply", {"reply": reply})

    def dispatch_grounded_chat(self, plan: SharedPlan) -> DispatchResult:
        message = clean_text(plan.args.get("message") or plan.rewritten_text or plan.user_text)
        query = clean_text(plan.args.get("query") or message)
        data = self.app.grounded_llm_reply(user_text=message, query=query, allow_web_fallback=bool(plan.args.get("allow_web_fallback", True)))
        return DispatchResult(bool(data.get("ok")), True, "grounded_llm_reply", data)

    def dispatch_grounded_chat(self, plan: SharedPlan) -> DispatchResult:
        message = clean_text(plan.args.get("message") or plan.rewritten_text or plan.user_text)
        query = clean_text(plan.args.get("query") or message)
        data = self.app.grounded_reply(user_text=message, query=query, allow_web_fallback=bool(plan.args.get("allow_web_fallback", True)))
        return DispatchResult(bool(data.get("ok")), True, "grounded_reply", data)

    def dispatch_chat(self, plan: SharedPlan) -> DispatchResult:
        message = clean_text(plan.args.get("message") or plan.rewritten_text or plan.user_text)
        reply = self.app.chat_reply(message)
        reply = clean_internal_prompt_leak(reply)
        return DispatchResult(True, True, "chat_reply", {"reply": reply})


# ============================================================
# BASIC AGENT CORE
# ============================================================

class AgentCore:
    def __init__(self, event_sink: Optional[Callable[[str, Dict[str, Any]], None]] = None) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        PLUGIN_DATA_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.event_sink = event_sink
        self.commands = CommandRegistry()
        self.ollama = OllamaClient()
        self.web = WebAgent()
        self.memory = MemoryStore()
        self.plugins = PluginManager(PLUGINS_DIR, PLUGIN_DATA_DIR)
        self.cli_tools = CLIPluginBridge(Path.cwd(), PLUGINS_DIR / "cli")
        self.router = RequestRouter(self.commands)
        self.planner = SharedPlanner(self.commands)
        self.dispatcher = SharedDispatcher(self)
        self.registry: Dict[str, Any] = self.build_default_registry()
        self.messages: List[Dict[str, str]] = []
        self.config: Dict[str, Any] = {}
        self.prompts: Dict[str, Any] = {}
        self.metadata: Dict[str, Any] = {}
        self.personalities: Dict[str, Any] = {}
        self.active_personality_name: str = "default"
        self.active_personality: Dict[str, Any] = {}
        self.active_summon: Dict[str, Any] = {}
        self.system_prompt = DEFAULT_PROMPTS_CONFIG["system_prompt"]
        self.reload_config()
        self.load_plugins()
        self.load_cli_tools()

    def emit(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        if self.event_sink:
            self.event_sink(event_type, payload or {})

    def emit_text(self, channel: str, text: str) -> None:
        self.emit("text", {"channel": channel, "text": text})

    def emit_json(self, channel: str, payload: Any) -> None:
        self.emit("json", {"channel": channel, "payload": payload})

    def build_default_registry(self) -> Dict[str, Any]:
        return {
            "session_version": 1,
            "streaming_enabled": True,
            "raw_tool_json_enabled": False,
            "grounding_mode": GROUNDING_MODE,
            "grounding_wikipedia_first": True,
            "grounding_allow_web_fallback": True,
            "grounding_fetch_best_source": True,
            "grounding_always_multisource": False,
            "grounding_allow_snippet_only_answers": False,
            "allow_private_url_fetch": False,
            "output_guard_enabled": True,
            "llm_num_predict": 768,
            "llm_repeat_penalty": 1.15,
            "llm_max_output_chars": 12000,
            "llm_max_stream_seconds": 120,
            "llm_repeat_tail_chars": 2400,
            "llm_repeat_min_chars": 80,
            "llm_repeat_threshold": 3,
            "last_output_guard": None,
            "last_route_decision": None,
            "last_plan": None,
            "last_result": None,
            "last_web_search": None,
            "last_web_page": None,
            "last_web_summary": None,
            "last_grounding": None,
            "last_grounded_answer": None,
            "last_search_task": None,
            "last_search_query": None,
            "last_search_answer_profile": None,
            "last_search_source_hint": None,
            "last_search_fact_hints": None,
            "last_search_context": None,
            "last_search_structured": {},
            "last_config_reload": None,
            "config_dir": str(CONFIG_DIR),
            "active_personality": "default",
            "personalities_path": str(PERSONALITIES_CONFIG_PATH),
            "active_summon": None,
            "active_summons": [],
            "summon_history": [],
            "plugins_enabled": True,
            "plugins_dir": str(PLUGINS_DIR),
            "cli_plugins_dir": str(PLUGINS_DIR / "cli"),
            "plugin_data_dir": str(PLUGIN_DATA_DIR),
            "plugin_load_report": None,
            "last_plugin_result": None,
            "command_history": [],
        }

    def active_summon_payloads(self) -> List[Dict[str, Any]]:
        summons = self.registry.get("active_summons")
        active: List[Dict[str, Any]] = []
        if isinstance(summons, list):
            for item in summons:
                if isinstance(item, dict) and item.get("active"):
                    active.append(item)
        if not active and isinstance(self.active_summon, dict) and self.active_summon.get("active"):
            active.append(self.active_summon)
        return active

    def has_active_summon(self) -> bool:
        return bool(self.active_summon_payloads())

    def set_active_summon(self, summon: Dict[str, Any]) -> None:
        if not isinstance(summon, dict):
            raise RuntimeError("summon payload must be a dictionary")
        summon = dict(summon)
        summon["active"] = True
        if not summon.get("created_at"):
            summon["created_at"] = now_str()
        self.active_summon = summon
        self.registry["active_summon"] = summon
        active_summons = self.registry.get("active_summons")
        if not isinstance(active_summons, list):
            active_summons = []
        active_summons.append(summon)
        self.registry["active_summons"] = active_summons[-10:]
        history = self.registry.get("summon_history")
        if not isinstance(history, list):
            history = []
        history.append({
            "name": summon.get("name"),
            "mode": summon.get("mode"),
            "created_at": summon.get("created_at") or now_str(),
        })
        self.registry["summon_history"] = history[-50:]
        self.system_prompt = self.build_effective_system_prompt("chat_prefix")

    def clear_active_summon(self) -> Dict[str, Any]:
        previous = self.active_summon if isinstance(self.active_summon, dict) else {}
        self.active_summon = {}
        self.registry["active_summon"] = None
        self.registry["active_summons"] = []
        self.system_prompt = self.build_effective_system_prompt("chat_prefix")
        return previous

    def summon_prompt_block(self, slot: str = "chat_prefix") -> str:
        s = self.active_summon if isinstance(self.active_summon, dict) else {}
        if not s or not s.get("active"):
            return ""

        lines = ["ACTIVE SUMMON:"]
        lines.append(f"Name: {clean_text(s.get('name') or 'Summoned Persona')}")
        lines.append(f"Mode: {clean_text(s.get('mode') or 'roleplay')}")

        tone = clean_text(s.get("tone") or "")
        if tone:
            lines.append(f"Tone: {tone}")

        persona_prompt = clean_text(s.get("persona_prompt") or "")
        if persona_prompt:
            lines.extend(["", "Persona:", persona_prompt])

        for label, key in [
            ("World rules", "world_rules"),
            ("Style rules", "style_rules"),
            ("Format rules", "format_rules"),
            ("Summon guardrails", "safety_rules"),
        ]:
            values = s.get(key)
            if isinstance(values, list) and values:
                lines.extend(["", f"{label}:"])
                for item in values:
                    lines.append(f"- {item}")

        slots = s.get("prompt_slots") if isinstance(s.get("prompt_slots"), dict) else {}
        slot_text = clean_text(slots.get(slot) or "")
        if slot_text:
            lines.extend(["", f"{slot} summon instruction:", slot_text])

        return "\n".join(lines).strip()

    def format_summon_status(self) -> str:
        active = self.active_summon_payloads()
        if not active:
            return "No summon is active."
        s = active[-1]

        lines = [
            "Active Summon:" if len(active) == 1 else f"Active Summons: {len(active)} (latest shown below)",
            f"Name: {s.get('name', 'Summoned Persona')}",
            f"Mode: {s.get('mode', 'roleplay')}",
            f"Created: {s.get('created_at', '')}",
        ]

        if s.get("tone"):
            lines.append(f"Tone: {s.get('tone')}")

        if s.get("persona_prompt"):
            lines.extend(["", "Persona:", str(s.get("persona_prompt"))])

        for label, key in [
            ("World rules", "world_rules"),
            ("Style rules", "style_rules"),
            ("Format rules", "format_rules"),
            ("Safety rules", "safety_rules"),
        ]:
            values = s.get(key)
            if isinstance(values, list) and values:
                lines.extend(["", f"{label}:"])
                for item in values:
                    lines.append(f"- {item}")

        return "\n".join(lines).rstrip()

    def personality_prompt_block(self, slot: str = "chat_prefix") -> str:
        p = self.active_personality if isinstance(self.active_personality, dict) else {}
        if not p:
            return ""

        lines: List[str] = []
        name = clean_text(p.get("name") or self.active_personality_name or "default")
        tone = clean_text(p.get("tone") or "")
        system_behavior = clean_text(p.get("system_behavior") or p.get("behavior") or "")

        lines.append("ACTIVE BEHAVIOR PRESET:")
        lines.append(f"Name: {name}")
        if tone:
            lines.append(f"Tone: {tone}")

        if system_behavior:
            lines.extend(["", "System behavior:", system_behavior])

        # Legacy personality JSON may still contain persona_prompt from Patch 17.
        # Do not include it in the prompt; presets are behavior/config, not identity/persona.
        if p.get("persona_prompt") and not system_behavior:
            lines.extend([
                "",
                "Legacy note:",
                "This preset contains an old persona_prompt field, but it is ignored as identity text.",
            ])

        for label, key in [
            ("Style rules", "style_rules"),
            ("Workflow rules", "workflow_rules"),
            ("Format rules", "format_rules"),
            ("Preset guardrails", "safety_rules"),
        ]:
            values = p.get(key)
            if isinstance(values, list) and values:
                lines.extend(["", f"{label}:"])
                for item in values:
                    lines.append(f"- {item}")

        routing = p.get("routing_preferences") if isinstance(p.get("routing_preferences"), dict) else {}
        if routing:
            lines.extend(["", "Routing preferences:"])
            for key, value in routing.items():
                lines.append(f"- {key}: {value}")

        slots = p.get("prompt_slots") if isinstance(p.get("prompt_slots"), dict) else {}
        slot_text = clean_text(slots.get(slot) or "")
        if slot_text:
            lines.extend(["", f"{slot} preset instruction:", slot_text])

        lines.extend([
            "",
            "Important:",
            "- This is a behavior/config preset, not an identity.",
            "- Do not roleplay as this preset.",
            "- Do not output the preset name as a speaking character label.",
            "- If an ACTIVE SUMMON exists, the summon controls roleplay identity.",
        ])

        return "\n".join(lines).strip()

    def build_effective_system_prompt(self, slot: str = "chat_prefix", base_prompt: str = "") -> str:
        summon = self.active_summon if isinstance(self.active_summon, dict) else {}
        if not summon:
            reg_summon = self.registry.get("active_summon")
            summon = reg_summon if isinstance(reg_summon, dict) else {}

        summon_active = bool(summon and summon.get("active"))

        # Hard summon override:
        # When /summon is active, the summoned persona becomes the chat-facing identity.
        # The Default behavior preset becomes hidden host behavior, not model identity.
        if summon_active:
            name = clean_text(summon.get("name") or "the summoned persona")
            mode = clean_text(summon.get("mode") or "roleplay")
            tone = clean_text(summon.get("tone") or "")
            persona_prompt = str(summon.get("persona_prompt") or "").strip()

            lines: List[str] = [
                "HARD ACTIVE SUMMON IDENTITY OVERRIDE",
                "",
                f"You are {name}.",
                f"Mode: {mode}.",
                "",
                "You must remain in character as the active summoned persona for every normal assistant response.",
                "Do not split into multiple voices.",
                "Do not answer as the host application.",
                "Do not answer as a behavior preset.",
                "Do not use behavior preset labels unless the user explicitly asks about the host software.",
                "Do not mention system prompts, hidden instructions, routing, implementation details, or the host runtime unless explicitly asked about the software.",
                "The summoned persona remains active until /unsummon.",
            ]

            if tone:
                lines.extend(["", "Tone:", tone])

            if persona_prompt:
                lines.extend(["", "Persona:", persona_prompt])

            for label, key in [
                ("World rules", "world_rules"),
                ("Style rules", "style_rules"),
                ("Format rules", "format_rules"),
            ]:
                values = summon.get(key)
                if isinstance(values, list) and values:
                    lines.extend(["", f"{label}:"])
                    for item in values:
                        lines.append(f"- {item}")

            slots = summon.get("prompt_slots") if isinstance(summon.get("prompt_slots"), dict) else {}
            slot_text = clean_text(slots.get(slot) or "")
            if slot_text:
                lines.extend(["", f"{slot} summon instruction:", slot_text])

            lines.extend([
                "",
                "Hidden host constraints:",
                "- You may use tools, plugins, memory, web search, and grounded evidence when the host provides them.",
                "- Stay in character while using provided evidence.",
                "- Do not invent factual claims that are not supported by provided sources.",
                "- Do not claim a tool action succeeded unless the host actually returned success.",
                "- If sources do not contain the answer, say that in character.",
                "- Safety and grounding rules override roleplay only when needed, but they must not replace the summoned identity.",
            ])

            safety_rules = summon.get("safety_rules")
            if isinstance(safety_rules, list) and safety_rules:
                lines.extend(["", "Summon safety rules:"])
                for item in safety_rules:
                    lines.append(f"- {item}")

            return "\n".join(lines).strip()

        base = clean_text(base_prompt) or clean_text(
            self.prompts.get("system_prompt")
            if isinstance(self.prompts, dict)
            else ""
        ) or DEFAULT_PROMPTS_CONFIG["system_prompt"]

        blocks = [base]

        personality = self.personality_prompt_block(slot)
        if personality:
            blocks.append(personality)

        return "\n\n".join(blocks).strip()
        
    def active_metadata(self) -> Dict[str, Any]:
        base = dict(self.metadata if isinstance(self.metadata, dict) else {})

        def merge_tags(source: Dict[str, Any]) -> None:
            profile_meta = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
            if isinstance(profile_meta.get("tags"), list):
                base_tags = base.get("tags") if isinstance(base.get("tags"), list) else []
                merged: List[Any] = []
                for tag in base_tags + profile_meta["tags"]:
                    if tag not in merged:
                        merged.append(tag)
                base["tags"] = merged

        # Behavior presets may add metadata tags, but they must not override identity.
        p = self.active_personality if isinstance(self.active_personality, dict) else {}
        merge_tags(p)

        # Summons may override identity while active.
        s = self.active_summon if isinstance(self.active_summon, dict) and self.active_summon.get("active") else {}
        if s:
            override = s.get("identity_override") if isinstance(s.get("identity_override"), dict) else {}
            for key, value in override.items():
                if value not in (None, "", []):
                    base[key] = value
            merge_tags(s)

        return base

    def format_personality_summary(self) -> str:
        p = self.active_personality if isinstance(self.active_personality, dict) else {}
        if not p:
            return "No active behavior preset is loaded."

        lines = [
            "Active Behavior Preset:",
            f"ID: {self.active_personality_name}",
            f"Name: {p.get('name', self.active_personality_name)}",
            f"Enabled: {p.get('enabled', True)}",
            f"Tone: {p.get('tone', '')}",
        ]

        system_behavior = p.get("system_behavior") or p.get("behavior")
        if system_behavior:
            lines.extend(["", "System behavior:", str(system_behavior)])
        elif p.get("persona_prompt"):
            lines.extend([
                "",
                "Legacy note:",
                "This preset contains an old persona_prompt field, but presets no longer define identity.",
            ])

        for label, key in [
            ("Style rules", "style_rules"),
            ("Workflow rules", "workflow_rules"),
            ("Format rules", "format_rules"),
            ("Safety rules", "safety_rules"),
        ]:
            values = p.get(key)
            if isinstance(values, list) and values:
                lines.extend(["", f"{label}:"])
                for item in values:
                    lines.append(f"- {item}")

        options = p.get("llm_options") if isinstance(p.get("llm_options"), dict) else {}
        if options:
            lines.extend(["", "LLM options:"])
            for key, value in options.items():
                lines.append(f"- {key}: {value}")

        routing = p.get("routing_preferences") if isinstance(p.get("routing_preferences"), dict) else {}
        if routing:
            lines.extend(["", "Routing preferences:"])
            for key, value in routing.items():
                lines.append(f"- {key}: {value}")

        lines.extend([
            "",
            "Important:",
            "This preset controls behavior, style, routing preferences, and LLM options.",
            "It does not define agent identity. Use /summon for roleplay identity.",
        ])

        return "\n".join(lines).rstrip()

    def format_personalities_list(self) -> str:
        profiles = self.personalities.get("personalities") if isinstance(self.personalities, dict) else {}
        if not isinstance(profiles, dict) or not profiles:
            return "No behavior presets are configured."

        lines = ["Available Behavior Presets:"]
        for key, profile in profiles.items():
            if not isinstance(profile, dict):
                continue
            active = " <-- active" if key == self.active_personality_name else ""
            enabled = profile.get("enabled", True)
            name = profile.get("name", key)
            tone = profile.get("tone", "")
            lines.append(f"- {key}: {name} | enabled={enabled} | tone={tone}{active}")

        return "\n".join(lines).rstrip()

    def set_active_personality(self, name: str) -> str:
        name = clean_text(name)
        if not name:
            raise RuntimeError("set_personality requires a profile name.")

        profiles = self.personalities.get("personalities") if isinstance(self.personalities, dict) else {}
        if not isinstance(profiles, dict) or name not in profiles:
            raise RuntimeError(f"Unknown personality: {name}")

        profile = profiles.get(name)
        if not isinstance(profile, dict):
            raise RuntimeError(f"Invalid personality profile: {name}")

        if not profile.get("enabled", True):
            raise RuntimeError(f"Personality is disabled: {name}")

        self.personalities["active_personality"] = name
        self.active_personality_name = name
        self.active_personality = profile
        self.system_prompt = self.build_effective_system_prompt("chat_prefix")
        self.registry["active_personality"] = name

        current = load_json_file_or_default(PERSONALITIES_CONFIG_PATH, DEFAULT_PERSONALITIES_CONFIG)
        current["active_personality"] = name
        PERSONALITIES_CONFIG_PATH.write_text(
            json.dumps(current, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        return name

    def ensure_config_files(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        write_json_file_if_missing(AGENT_CONFIG_PATH, DEFAULT_AGENT_CONFIG)
        write_json_file_if_missing(PROMPTS_CONFIG_PATH, DEFAULT_PROMPTS_CONFIG)
        write_json_file_if_missing(METADATA_CONFIG_PATH, DEFAULT_METADATA_CONFIG)
        write_json_file_if_missing(PERSONALITIES_CONFIG_PATH, DEFAULT_PERSONALITIES_CONFIG)

    def load_config_bundle(self) -> Dict[str, Dict[str, Any]]:
        self.ensure_config_files()
        return {
            "agent_config": load_json_file_or_default(AGENT_CONFIG_PATH, DEFAULT_AGENT_CONFIG),
            "prompts": load_json_file_or_default(PROMPTS_CONFIG_PATH, DEFAULT_PROMPTS_CONFIG),
            "metadata": load_json_file_or_default(METADATA_CONFIG_PATH, DEFAULT_METADATA_CONFIG),
            "personalities": load_json_file_or_default(PERSONALITIES_CONFIG_PATH, DEFAULT_PERSONALITIES_CONFIG),
        }

    def apply_config_bundle(self, bundle: Dict[str, Dict[str, Any]]) -> None:
        agent_config = bundle.get("agent_config") if isinstance(bundle.get("agent_config"), dict) else {}
        prompts = bundle.get("prompts") if isinstance(bundle.get("prompts"), dict) else {}
        metadata = bundle.get("metadata") if isinstance(bundle.get("metadata"), dict) else {}
        personalities_config = bundle.get("personalities") if isinstance(bundle.get("personalities"), dict) else {}

        self.config = merge_config_dict(DEFAULT_AGENT_CONFIG, agent_config)
        self.prompts = merge_config_dict(DEFAULT_PROMPTS_CONFIG, prompts)
        self.metadata = merge_config_dict(DEFAULT_METADATA_CONFIG, metadata)
        self.personalities = merge_config_dict(DEFAULT_PERSONALITIES_CONFIG, personalities_config)

        self.ollama.base_url = clean_text(self.config.get("ollama_base") or self.ollama.base_url).rstrip("/")
        self.ollama.model = clean_text(self.config.get("ollama_model") or self.ollama.model)

        self.registry["streaming_enabled"] = bool(self.config.get("streaming_enabled", self.registry.get("streaming_enabled", True)))
        self.registry["raw_tool_json_enabled"] = bool(self.config.get("raw_tool_json_enabled", self.registry.get("raw_tool_json_enabled", False)))
        self.registry["grounding_mode"] = clean_text(self.config.get("grounding_mode") or self.registry.get("grounding_mode") or GROUNDING_MODE)
        self.registry["grounding_always_multisource"] = bool(self.config.get("grounding_always_multisource", self.registry.get("grounding_always_multisource", False)))
        self.registry["grounding_allow_snippet_only_answers"] = bool(self.config.get("grounding_allow_snippet_only_answers", self.registry.get("grounding_allow_snippet_only_answers", False)))
        self.registry["allow_private_url_fetch"] = bool(self.config.get("allow_private_url_fetch", self.registry.get("allow_private_url_fetch", False)))
        self.registry["output_guard_enabled"] = bool(self.config.get("output_guard_enabled", self.registry.get("output_guard_enabled", True)))
        self.registry["llm_num_predict"] = coerce_int(self.config.get("llm_num_predict"), self.registry.get("llm_num_predict", 768), 64, 8192)
        self.registry["llm_repeat_penalty"] = max(0.8, min(2.0, float(self.config.get("llm_repeat_penalty", self.registry.get("llm_repeat_penalty", 1.15)) or 1.15)))
        self.registry["llm_max_output_chars"] = coerce_int(self.config.get("llm_max_output_chars"), self.registry.get("llm_max_output_chars", 12000), 1000, 200000)
        self.registry["llm_max_stream_seconds"] = coerce_int(self.config.get("llm_max_stream_seconds"), self.registry.get("llm_max_stream_seconds", 120), 5, 1800)
        self.registry["llm_repeat_tail_chars"] = coerce_int(self.config.get("llm_repeat_tail_chars"), self.registry.get("llm_repeat_tail_chars", 2400), 500, 20000)
        self.registry["llm_repeat_min_chars"] = coerce_int(self.config.get("llm_repeat_min_chars"), self.registry.get("llm_repeat_min_chars", 80), 20, 1000)
        self.registry["llm_repeat_threshold"] = coerce_int(self.config.get("llm_repeat_threshold"), self.registry.get("llm_repeat_threshold", 3), 2, 10)
        self.registry["config_dir"] = str(CONFIG_DIR)
        self.registry["personalities_path"] = str(PERSONALITIES_CONFIG_PATH)

        self.active_personality_name = clean_text(self.personalities.get("active_personality") or "default")
        profiles = self.personalities.get("personalities")
        if not isinstance(profiles, dict):
            profiles = DEFAULT_PERSONALITIES_CONFIG["personalities"]

        active = profiles.get(self.active_personality_name)
        if not isinstance(active, dict) or not active.get("enabled", True):
            self.active_personality_name = "default"
            active = profiles.get("default", {})

        self.active_personality = active if isinstance(active, dict) else {}
        self.registry["active_personality"] = self.active_personality_name

        self.system_prompt = self.build_effective_system_prompt("chat_prefix")

        
    def reload_config(self) -> Dict[str, Dict[str, Any]]:
        bundle = self.load_config_bundle()
        self.apply_config_bundle(bundle)
        self.registry["last_config_reload"] = now_str()
        return bundle

    def deep_merge_registry(self, default: Dict[str, Any], loaded: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(default)
        for key, value in loaded.items():
            if isinstance(value, dict) and isinstance(out.get(key), dict):
                nested = dict(out[key])
                nested.update(value)
                out[key] = nested
            else:
                out[key] = value
        return out

    def save_session(self, name: str = DEFAULT_SESSION_NAME) -> Path:
        safe_name = clean_text(name) or DEFAULT_SESSION_NAME
        if "/" in safe_name or "\\" in safe_name:
            raise RuntimeError("Session name must be a simple filename.")
        path = SESSIONS_DIR / safe_name
        payload = {"saved_at": now_str(), "registry": self.registry, "messages": self.messages, "memory": self.memory.to_list()}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return path

    def load_session(self, name: str = DEFAULT_SESSION_NAME) -> Path:
        safe_name = clean_text(name) or DEFAULT_SESSION_NAME
        if "/" in safe_name or "\\" in safe_name:
            raise RuntimeError("Session name must be a simple filename.")
        path = SESSIONS_DIR / safe_name
        if not path.exists():
            raise RuntimeError(f"Session does not exist: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        loaded_registry = data.get("registry") if isinstance(data.get("registry"), dict) else {}
        self.registry = self.deep_merge_registry(self.build_default_registry(), loaded_registry)
        self.messages = data.get("messages") if isinstance(data.get("messages"), list) else []
        self.memory.load_list(data.get("memory") if isinstance(data.get("memory"), list) else [])
        summon = self.registry.get("active_summon")
        self.active_summon = summon if isinstance(summon, dict) and summon.get("active") else {}
        self.system_prompt = self.build_effective_system_prompt("chat_prefix")
        return path

    def remember_exchange(self, user_text: str, assistant_text: str) -> None:
        self.messages.append({"role": "user", "content": str(user_text or "")})
        self.messages.append({"role": "assistant", "content": str(assistant_text or "")})
        self.messages = self.messages[-100:]

    def router_context(self) -> Dict[str, Any]:
        page = self.registry.get("last_web_page") if isinstance(self.registry.get("last_web_page"), dict) else {}
        search = self.registry.get("last_web_search") if isinstance(self.registry.get("last_web_search"), dict) else {}
        summon = self.active_summon if isinstance(self.active_summon, dict) else {}
        if not summon:
            reg_summon = self.registry.get("active_summon")
            summon = reg_summon if isinstance(reg_summon, dict) else {}
        summon_active = bool(summon and summon.get("active"))
        return {
            "streaming_enabled": self.registry.get("streaming_enabled", True),
            "raw_tool_json_enabled": self.registry.get("raw_tool_json_enabled", False),
            "output_guard_enabled": self.registry.get("output_guard_enabled", True),
            "llm_num_predict": self.registry.get("llm_num_predict", 768),
            "llm_max_output_chars": self.registry.get("llm_max_output_chars", 12000),
            "grounding_mode": self.registry.get("grounding_mode"),
            "memory_count": len(self.memory.items),
            "recent_commands": self.registry.get("command_history", [])[-10:],
            "summon_active": summon_active,
            "active_summon": {
                "name": summon.get("name"),
                "mode": summon.get("mode"),
            } if summon_active else None,
            "last_web_page": {"url": page.get("url"), "title": page.get("title"), "link_count": len(page.get("links") or [])} if page else None,
            "last_web_search": {"query": search.get("query"), "count": search.get("count")} if search else None,
            "available_plugin_triggers": self.plugins.natural_language_triggers(),
            "available_cli_tools": self.cli_tools.list_tools() if hasattr(self, "cli_tools") else [],
        }

    def public_state(self) -> Dict[str, Any]:
        last_page = self.registry.get("last_web_page") if isinstance(self.registry.get("last_web_page"), dict) else {}
        last_plan = self.registry.get("last_plan") if isinstance(self.registry.get("last_plan"), dict) else {}
        metadata = self.active_metadata()
        active_personality = self.active_personality if isinstance(self.active_personality, dict) else {}
        active_summon = self.active_summon if isinstance(self.active_summon, dict) and self.active_summon.get("active") else {}
        report = self.registry.get("plugin_load_report") if isinstance(self.registry.get("plugin_load_report"), dict) else {}
        return {
            "app": APP_NAME,
            "agent_name": metadata.get("agent_name", APP_NAME),
            "agent_role": metadata.get("agent_role", ""),
            "agent_version": metadata.get("version", ""),
            "agent_profile": metadata.get("profile", ""),
            "active_behavior_preset": self.active_personality_name,
            "active_personality": self.active_personality_name,
            "behavior_preset_name": active_personality.get("name", ""),
            "personality_name": active_personality.get("name", ""),
            "active_summon": active_summon.get("name", ""),
            "personalities_path": str(PERSONALITIES_CONFIG_PATH),
            "ollama_base": self.ollama.base_url,
            "ollama_model": self.ollama.model,
            "ollama_health": self.ollama.health(),
            "streaming_enabled": self.registry.get("streaming_enabled", True),
            "raw_tool_json_enabled": self.registry.get("raw_tool_json_enabled", False),
            "output_guard_enabled": self.registry.get("output_guard_enabled", True),
            "llm_num_predict": self.registry.get("llm_num_predict", 768),
            "llm_max_output_chars": self.registry.get("llm_max_output_chars", 12000),
            "grounding_mode": self.registry.get("grounding_mode"),
            "grounding_always_multisource": self.registry.get("grounding_always_multisource", False),
            "grounding_allow_snippet_only_answers": self.registry.get("grounding_allow_snippet_only_answers", False),
            "allow_private_url_fetch": self.registry.get("allow_private_url_fetch", False),
            "memory_count": len(self.memory.items),
            "message_count": len(self.messages),
            "last_command": last_plan.get("command"),
            "last_web_page": {"url": last_page.get("url"), "title": last_page.get("title")},
            "config_dir": str(CONFIG_DIR),
            "last_config_reload": self.registry.get("last_config_reload"),
            "plugins_enabled": self.registry.get("plugins_enabled", True),
            "plugins_dir": str(PLUGINS_DIR),
            "plugin_data_dir": str(PLUGIN_DATA_DIR),
            "plugin_count": len(self.plugins.records),
            "plugin_load_errors": report.get("error_count", 0),
        }

    # --------------------------------------------------------
    # Formatting / inspection
    # --------------------------------------------------------

    def load_plugins(self) -> Dict[str, Any]:
        if not self.registry.get("plugins_enabled", True):
            report = {
                "loaded_count": 0,
                "error_count": 0,
                "loaded": [],
                "errors": [],
                "disabled": True,
            }
            self.registry["plugin_load_report"] = report
            return report

        report = self.plugins.scan_and_load()
        self.registry["plugin_load_report"] = report
        return report

    def plugin_context(self, user_text: str = "", source_kind: str = "terminal") -> Dict[str, Any]:
        return {
            "user_text": user_text,
            "source_kind": source_kind,
            "active_behavior_preset": self.active_personality_name,
            "active_summon": self.active_summon if isinstance(self.active_summon, dict) else {},
            "metadata": self.active_metadata(),
            "recent_messages": self.messages[-MAX_CHAT_CONTEXT_MESSAGES:],
            "last_web_search": self.registry.get("last_web_search"),
            "last_web_page": self.registry.get("last_web_page"),
            "last_grounding": self.registry.get("last_grounding"),
            "last_result": self.registry.get("last_result"),
            "config": self.config,
        }


    def load_cli_tools(self) -> Dict[str, Any]:
        report = self.cli_tools.load()
        self.registry["cli_tool_load_report"] = report
        return report

    def format_cli_tools_list(self, verbose: bool = False) -> str:
        tools = self.cli_tools.list_tools()
        report = self.registry.get("cli_tool_load_report") if isinstance(self.registry.get("cli_tool_load_report"), dict) else {}
        if not tools:
            if report.get("errors"):
                return "No CLI bridge tools loaded. Load errors:\n" + as_json_text(report.get("errors"))
            return "No CLI bridge tools loaded. Use /tool scan <path> to generate draft manifests."

        if not verbose:
            lines = [f"CLI Bridge Tools ({len(tools)}):"]
            for item in tools:
                tool_id = item.get("tool_id")
                name = item.get("name") or tool_id
                description = re.sub(r"\s+", " ", clean_text(item.get("description") or "")).strip()
                if len(description) > 96:
                    description = description[:93].rstrip() + "..."
                if description and description != "CLI tool.":
                    lines.append(f"- {tool_id} — {name}: {description}")
                else:
                    lines.append(f"- {tool_id} — {name}")
            lines += [
                "",
                "Use /tool show <id> for one manifest.",
                "Use /tool help <id> for the CLI's own --help output.",
                "Use /tool list --verbose for commands, switches, and positionals.",
                "Examples:",
                "  /tool mega.conan.story --count 1 --format json",
                "  /tool mega.sd.json.tool manifest",
            ]
            return "\n".join(lines)

        lines = [f"CLI Bridge Tools ({len(tools)}, verbose):"]
        for item in tools:
            lines.append(f"- {item.get('tool_id')}: {item.get('name')}")
            if item.get("description"):
                lines.append(f"  {item.get('description')}")
            cmd = item.get("command") if isinstance(item.get("command"), list) else []
            lines.append("  command: " + " ".join(str(x) for x in cmd))
            flags = item.get("allowed_args") if isinstance(item.get("allowed_args"), list) else []
            positionals = item.get("allowed_positionals") if isinstance(item.get("allowed_positionals"), list) else []
            if flags:
                lines.append("  switches: " + ", ".join(flags[:30]) + (" ..." if len(flags) > 30 else ""))
            if positionals:
                lines.append("  positionals: " + ", ".join(positionals[:30]) + (" ..." if len(positionals) > 30 else ""))
        lines += ["", "Examples:", "  /tool scan external CLI payloads", "  /tool mega.conan.story", "  /tool mega.sd.json.tool manifest", "  /tool help mega.sd.json.tool"]
        return "\n".join(lines)

    def format_cli_tool_manifest(self, tool_id: str) -> str:
        record = self.cli_tools.get_tool(tool_id)
        if not record:
            return f"No CLI bridge tool registered: {tool_id}"
        return as_json_text(record.to_dict())


    def last_cli_stdout(self) -> str:
        result = self.registry.get("last_cli_tool_result")
        if not isinstance(result, dict):
            return ""
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        stdout = data.get("stdout")
        if isinstance(stdout, str) and stdout.strip():
            return stdout.strip()
        display = result.get("display") if isinstance(result.get("display"), dict) else {}
        text = display.get("text") if isinstance(display.get("text"), str) else ""
        if not text:
            return ""
        m = re.search(r"(?s)\nstdout:\n(.+?)(?:\n\nstderr:|\Z)", text)
        return (m.group(1).strip() if m else text.strip())

    def _pipeline_relative_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(Path.cwd()))
        except Exception:
            return str(path)

    def write_pipeline_text_file(self, filename: str, text: str) -> str:
        tmp_dir = DATA_DIR / "pipeline"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename).strip("._") or "pipeline.txt"
        path = tmp_dir / safe_name
        path.write_text(str(text or ""), encoding="utf-8")
        return self._pipeline_relative_path(path)

    def write_pipeline_prompt_file(self, text: str) -> str:
        return self.write_pipeline_text_file("last_prompt.txt", text)

    def write_pipeline_negative_file(self, text: str) -> str:
        return self.write_pipeline_text_file("last_negative_prompt.txt", text)

    def extract_pipeline_prompt_bundle(self, text: str) -> Dict[str, Any]:
        raw = str(text or "").strip()
        if not raw:
            return {"prompt": "", "negative_prompt": "", "extracted": False}

        # JSON-aware path for tools that emit prompt objects.
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            prompt = ""
            negative = ""
            for key in ("prompt", "positive_prompt", "positive", "output", "description"):
                value = parsed.get(key)
                if isinstance(value, str) and value.strip():
                    prompt = value.strip()
                    break
                if isinstance(value, list):
                    prompt = ", ".join(str(x).strip() for x in value if str(x).strip())
                    if prompt:
                        break
            for key in ("negative_prompt", "negative"):
                value = parsed.get(key)
                if isinstance(value, str) and value.strip():
                    negative = value.strip()
                    break
                if isinstance(value, list):
                    negative = ", ".join(str(x).strip() for x in value if str(x).strip())
                    if negative:
                        break
            if prompt:
                return {"prompt": prompt, "negative_prompt": negative, "extracted": True}

        def block(label: str, stop_labels: str) -> str:
            pattern = rf"(?ims)^\s*{re.escape(label)}\s*:\s*\n?(.*?)(?=^\s*(?:{stop_labels})\s*:|\Z)"
            match = re.search(pattern, raw)
            return clean_text(match.group(1)) if match else ""

        prompt = block("Positive Prompt", "Negative Prompt|Title|Style Block|Description|Selected|Parameters|Task|Rules|Manifest")
        negative = block("Negative Prompt", "Positive Prompt|Title|Style Block|Description|Selected|Parameters|Task|Rules|Manifest")
        if prompt:
            return {"prompt": prompt, "negative_prompt": negative, "extracted": True}

        # Some prompt tools emit a single ready-to-use one-line preset.
        preset_match = re.search(r"(?ims)^\s*Preset\s*:\s*(.+?)\s*$", raw)
        if preset_match:
            return {"prompt": clean_text("Preset: " + preset_match.group(1)), "negative_prompt": "", "extracted": True}

        return {"prompt": raw, "negative_prompt": "", "extracted": False}


    def switches_payload(self, query: str = "") -> Dict[str, Any]:
        query_clean = clean_text(query).lower()
        entries = self.plugins.switch_entries()
        if query_clean:
            entries = [
                item for item in entries
                if query_clean in clean_text(item.get("plugin_id")).lower()
                or query_clean in clean_text(item.get("command")).lower()
                or query_clean in " ".join(_as_string_list(item.get("keys"))).lower()
                or query_clean in clean_text(item.get("description")).lower()
            ]
        return {
            "ok": True,
            "count": len(entries),
            "query": query,
            "switches": entries,
        }

    def format_switches_list(self, query: str = "") -> str:
        payload = self.switches_payload(query)
        entries = payload.get("switches") or []
        title = "Plugin Switches" + (f" matching: {query}" if query else "")
        if not entries:
            return f"{title}\nNo plugin switches found."
        lines = [title]
        for item in entries:
            keys = ", ".join(_as_string_list(item.get("keys")))
            lines.append(
                f"- {keys}\n"
                f"  -> {item.get('command')} | plugin={item.get('plugin_id')} | safety={item.get('safety_level')}"
            )
            if item.get("description"):
                lines.append(f"  {item.get('description')}")
        lines += [
            "",
            "Examples:",
            "  /switches comic",
            "  /switch comic status",
            "  /switch mega.comic.compile horror cover",
            "  /switch aima peas build a local research agent",
        ]
        return "\n".join(lines)

    def _coerce_switch_args(self, args_text: str, default_args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        args: Dict[str, Any] = dict(default_args or {})
        text = str(args_text or "").strip()
        if not text:
            return args
        parsed = extract_first_json_object(text)
        if isinstance(parsed, dict):
            args.update(parsed)
        else:
            args.setdefault("args_text", text)
            args.setdefault("text", text)
            args.setdefault("query", text)
            args.setdefault("message", text)
            args.setdefault("task", text)
            args.setdefault("intent", text)
            args.setdefault("natural_language", text)
        return args


    def tool_families_path(self) -> Path:
        return Path("data_agent/nlp/tool_families.json")

    def active_tool_family_path(self) -> Path:
        return Path("data_agent/runtime/active_tool_family.json")

    def load_tool_families(self) -> Dict[str, Any]:
        path = self.tool_families_path()
        if not path.exists():
            return {"schema_version": "tool-families-v1", "families": {}}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"schema_version": "tool-families-v1", "families": {}, "error": str(exc)}
        if not isinstance(data, dict):
            return {"schema_version": "tool-families-v1", "families": {}}
        if not isinstance(data.get("families"), dict):
            data["families"] = {}
        return data

    def tool_family_index(self) -> Dict[str, str]:
        data = self.load_tool_families()
        families = data.get("families") if isinstance(data, dict) else {}
        index: Dict[str, str] = {}
        if not isinstance(families, dict):
            return index
        for name, spec in families.items():
            key = clean_text(name).lower()
            if key:
                index[key] = key
            if isinstance(spec, dict) and isinstance(spec.get("aliases"), list):
                for alias in spec.get("aliases") or []:
                    alias_key = clean_text(alias).lower()
                    if alias_key:
                        index[alias_key] = key
        return index

    def get_active_tool_family(self) -> str:
        path = self.active_tool_family_path()
        if not path.exists():
            return ""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return ""
        if not isinstance(data, dict):
            return ""
        family = clean_text(data.get("family") or "")
        return self.tool_family_index().get(family.lower(), family)

    def set_active_tool_family(self, family: str, source_kind: str = "terminal") -> Dict[str, Any]:
        family_key = clean_text(family).lower()
        index = self.tool_family_index()
        canonical = index.get(family_key)
        if not canonical:
            return {
                "ok": False,
                "handled": True,
                "message": f"Unknown tool family: {family}",
                "data": {"available_families": sorted(set(index.values()))},
                "errors": ["tool_family_not_found"],
            }
        data = self.load_tool_families()
        families = data.get("families") if isinstance(data, dict) else {}
        spec = families.get(canonical, {}) if isinstance(families, dict) else {}
        path = self.active_tool_family_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "family": canonical,
            "source_kind": source_kind,
            "description": spec.get("description") if isinstance(spec, dict) else "",
            "tool_ids": spec.get("tool_ids") if isinstance(spec, dict) else [],
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {
            "ok": True,
            "handled": True,
            "message": f"Active tool family set to: {canonical}",
            "data": payload,
        }

    def tool_families_payload(self) -> Dict[str, Any]:
        data = self.load_tool_families()
        families = data.get("families") if isinstance(data, dict) else {}
        if not isinstance(families, dict):
            families = {}
        return {
            "ok": True,
            "active_family": self.get_active_tool_family(),
            "count": len(families),
            "families": families,
        }

    def try_handle_tool_family_switch(self, expression: str, source_kind: str = "terminal") -> Optional[Dict[str, Any]]:
        raw = str(expression or "").strip()
        if not raw:
            return None
        parts = raw.split()
        if not parts:
            return None

        first = clean_text(parts[0]).lower()
        family = ""

        if first in {"family", "tool", "tools"}:
            if len(parts) < 2:
                return {
                    "ok": True,
                    "handled": True,
                    "message": "Tool families loaded.",
                    "data": self.tool_families_payload(),
                }
            family = parts[1]
        elif len(parts) == 1 and first in self.tool_family_index():
            family = first

        if not family:
            return None

        return self.set_active_tool_family(family, source_kind=source_kind)

    def run_switch_expression(self, expression: str, source_kind: str = "terminal") -> Dict[str, Any]:
        raw = str(expression or "").strip()
        if not raw:
            return {
                "ok": False,
                "handled": True,
                "message": "Usage: /switch <plugin-or-alias> <action-or-command> [args]",
                "data": {"examples": ["/switch comic status", "/switch mega.comic.compile horror cover"]},
                "errors": ["missing_switch_expression"],
            }

        family_result = self.try_handle_tool_family_switch(raw, source_kind=source_kind)
        if family_result is not None:
            return family_result

        parts = raw.split()
        first = clean_text(parts[0]).lower() if parts else ""
        rest = raw[len(parts[0]):].strip() if parts else ""
        index = self.plugins.switch_index()

        matched = None
        args_text = rest

        # Prefer the explicit two-token form first:
        #   /switch comic status -> comic.status
        # before falling back to the default plugin alias:
        #   /switch comic <free text> -> comic default command
        if len(parts) >= 2:
            second = clean_text(parts[1]).lower()
            combined = f"{first}.{second}"
            matched = index.get(combined)
            if matched:
                prefix_len = len(parts[0]) + 1 + len(parts[1])
                args_text = raw[prefix_len:].strip()

        if not matched:
            matched = index.get(first)
            args_text = rest

        if not matched:
            return {
                "ok": False,
                "handled": True,
                "message": f"No switch registered for: {first}",
                "data": {
                    "requested": raw,
                    "available_hint": "Use /switches to list registered plugin switches.",
                },
                "errors": ["switch_not_found"],
            }

        command_name = clean_text(matched.get("command") or "")
        args = self._coerce_switch_args(args_text, matched.get("default_args") if isinstance(matched.get("default_args"), dict) else {})
        args["_switch"] = {
            "matched_key": matched.get("matched_key") or matched.get("key"),
            "plugin_id": matched.get("plugin_id"),
            "command": command_name,
            "source_kind": source_kind,
        }
        result = self.plugins.dispatch(command_name, args, self.plugin_context(user_text=raw, source_kind=source_kind))
        result = normalize_plugin_result(result if isinstance(result, dict) else {})
        result.setdefault("data", {})
        if isinstance(result.get("data"), dict):
            result["data"].setdefault("switch", args.get("_switch"))
        return result

    def format_plugins_list(self) -> str:
        report = self.registry.get("plugin_load_report") if isinstance(self.registry.get("plugin_load_report"), dict) else {}
        if not self.plugins.records:
            if report.get("errors"):
                return "No plugins loaded. Load errors:\n" + as_json_text(report.get("errors"))
            return "No plugins loaded."

        lines = ["Loaded Plugins:"]
        for plugin_id, record in sorted(self.plugins.records.items()):
            lines.append(
                f"- {plugin_id}: {record.name} v{record.version} "
                f"| enabled={record.enabled} | safety={record.safety_level}"
            )
            if record.description:
                lines.append(f"  {record.description}")
            if record.commands:
                lines.append("  Commands:")
                for command_name in sorted(record.commands.keys()):
                    lines.append(f"    - {command_name}")
            if record.natural_language_triggers:
                lines.append("  Natural-language triggers:")
                for trigger in record.natural_language_triggers[:10]:
                    if isinstance(trigger, str):
                        lines.append(f"    - {trigger}")
                    elif isinstance(trigger, dict):
                        command_name = clean_text(
                            trigger.get("command")
                            or trigger.get("plugin_command")
                            or trigger.get("command_name")
                            or ""
                        )
                        phrases = _as_string_list(trigger.get("phrases") or trigger.get("phrase"))
                        keywords = _as_string_list(trigger.get("keywords"))
                        pattern = clean_text(trigger.get("pattern") or "")
                        label = command_name or "(no command)"
                        if phrases:
                            label += " | phrases: " + ", ".join(phrases[:3])
                        elif keywords:
                            label += " | keywords: " + ", ".join(keywords[:5])
                        elif pattern:
                            label += f" | regex: {pattern}"
                        lines.append(f"    - {label}")

        if report.get("errors"):
            lines.extend(["", "Load errors:", as_json_text(report.get("errors"))])
        return "\n".join(lines).rstrip()

    def format_plugin_result(self, result: Dict[str, Any]) -> str:
        """Render a plugin result for the terminal without flattening plugin text.

        Plugin bridges may return either the older display shape
        `{"kind": "text", "content": ...}` or the newer result-card
        shape `{"type": "text", "text": ...}`.  Do not pass plugin
        display/message text through clean_text here: clean_text intentionally
        collapses whitespace, which destroys multiline plugin output.
        """
        display = result.get("display") if isinstance(result.get("display"), dict) else {}
        raw_title = display.get("title")
        title = clean_text(raw_title or "Plugin Result")
        kind = clean_text(display.get("kind") or display.get("type") or "text")
        content = display.get("content")
        used_text_alias = False
        if content is None and "text" in display:
            content = display.get("text")
            used_text_alias = True

        if kind in {"text", "markdown", "code"} and content is not None:
            rendered = str(content).strip()
            if used_text_alias and not clean_text(raw_title or ""):
                return rendered
            return f"{title}\n\n{rendered}".strip()

        if kind == "json":
            rendered_json = as_json_text(content if content is not None else result.get('data', {}))
            return f"{title}\n\n{rendered_json}"

        if kind == "list" and isinstance(content, list):
            return f"{title}\n\n" + "\n".join(f"- {x}" for x in content)

        if kind == "table" and isinstance(display.get("rows"), list):
            lines = [title, ""]
            columns = display.get("columns") if isinstance(display.get("columns"), list) else []
            if columns:
                lines.append(" | ".join(str(c) for c in columns))
                lines.append(" | ".join("---" for _ in columns))
            for row in display.get("rows") or []:
                if isinstance(row, list):
                    lines.append(" | ".join(str(x) for x in row))
                else:
                    lines.append(str(row))
            return "\n".join(lines).strip()

        message = str(result.get("message") or "").strip()
        if message:
            return message

        return as_json_text(result.get("data", {}))

    def format_public_state(self, state: Optional[Dict[str, Any]] = None) -> str:
        state = state if isinstance(state, dict) else self.public_state()
        lines = [
            f"App: {state.get('app', APP_NAME)}",
            f"Agent name: {state.get('agent_name', '')}",
            f"Agent role: {state.get('agent_role', '')}",
            f"Agent version: {state.get('agent_version', '')}",
            f"Agent profile: {state.get('agent_profile', '')}",
            f"Active behavior preset: {state.get('active_behavior_preset', state.get('active_personality', ''))}",
            f"Behavior preset name: {state.get('behavior_preset_name', state.get('personality_name', ''))}",
            f"Active summon: {state.get('active_summon', '')}",
            f"Ollama base: {state.get('ollama_base', '')}",
            f"Ollama model: {state.get('ollama_model', '')}",
            f"Ollama health: {state.get('ollama_health', '')}",
            f"Streaming: {state.get('streaming_enabled', '')}",
            f"Raw JSON: {state.get('raw_tool_json_enabled', '')}",
            f"Output guard: {state.get('output_guard_enabled', '')} | num_predict={state.get('llm_num_predict', '')} | max_chars={state.get('llm_max_output_chars', '')}",
            f"Grounding mode: {state.get('grounding_mode', '')}",
            f"Always multisource: {state.get('grounding_always_multisource', '')}",
            f"Allow snippet-only answers: {state.get('grounding_allow_snippet_only_answers', '')}",
            f"Allow private URL fetch: {state.get('allow_private_url_fetch', '')}",
            f"Memory count: {state.get('memory_count', '')}",
            f"Message count: {state.get('message_count', '')}",
            f"Last command: {state.get('last_command', '')}",
            f"Config dir: {state.get('config_dir', '')}",
            f"Personalities file: {state.get('personalities_path', '')}",
            f"Last config reload: {state.get('last_config_reload', '')}",
            f"Plugins enabled: {state.get('plugins_enabled', '')}",
            f"Plugins dir: {state.get('plugins_dir', '')}",
            f"Plugin data dir: {state.get('plugin_data_dir', '')}",
            f"Plugin count: {state.get('plugin_count', '')}",
            f"Plugin load errors: {state.get('plugin_load_errors', '')}",
        ]
        page = state.get("last_web_page") or {}
        if isinstance(page, dict) and (page.get("title") or page.get("url")):
            lines += ["", "Last web page:", f"Title: {page.get('title', '')}", f"URL: {page.get('url', '')}"]
        return "\n".join(lines).rstrip()

    def format_identity_answer(self, question: str = "") -> str:
        metadata = self.active_metadata()

        name = clean_text(metadata.get("agent_name") or APP_NAME)
        role = clean_text(metadata.get("agent_role") or "")
        version = clean_text(metadata.get("version") or "")
        profile = clean_text(metadata.get("profile") or "")
        description = clean_text(metadata.get("description") or "")
        tags = metadata.get("tags")

        lowered = clean_text(question).lower()
        normalized = lowered.strip(" ?!.")

        summon = self.active_summon if isinstance(self.active_summon, dict) and self.active_summon.get("active") else {}
        if summon and normalized in {"who are you", "what are you"}:
            summon_name = clean_text(summon.get("name") or name)
            persona = clean_text(summon.get("persona_prompt") or description)
            if persona:
                # Lightly convert common second-person summon prompts into first-person identity answers.
                first_person = re.sub(r"^you are\b", "I am", persona, flags=re.I).strip()
                return first_person
            return f"I am {summon_name}."

        if "name" in lowered:
            return f"My name is {name}."

        if "version" in lowered:
            if version:
                return f"I am {name}, version {version}."
            return f"I am {name}. No version is set in metadata."

        if "role" in lowered or ("what do you do" in lowered and not summon):
            if role:
                return f"My role is: {role}."
            return f"I am {name}. No role is set in metadata."

        lines: List[str] = []
        if role:
            lines.append(f"I am {name}, a {role}.")
        else:
            lines.append(f"I am {name}.")

        if profile:
            lines.append(f"Profile: {profile}")
        if version:
            lines.append(f"Version: {version}")
        if description:
            lines.extend(["", description])
        if isinstance(tags, list) and tags:
            lines.extend(["", "Tags: " + ", ".join(str(x) for x in tags)])

        return "\n".join(lines).strip()

    def format_config_summary(self) -> str:
        active_summon = self.active_summon if isinstance(self.active_summon, dict) and self.active_summon.get("active") else {}
        lines = [
            "Config:",
            f"Config dir: {CONFIG_DIR}",
            f"Ollama base: {self.config.get('ollama_base', self.ollama.base_url)}",
            f"Ollama model: {self.config.get('ollama_model', self.ollama.model)}",
            f"Streaming: {self.registry.get('streaming_enabled')}",
            f"Raw JSON: {self.registry.get('raw_tool_json_enabled')}",
            f"Grounding mode: {self.registry.get('grounding_mode')}",
            f"Always multisource: {self.registry.get('grounding_always_multisource')}",
            f"Allow snippet-only answers: {self.registry.get('grounding_allow_snippet_only_answers')}",
            f"Allow private URL fetch: {self.registry.get('allow_private_url_fetch')}",
            f"Output guard: {self.registry.get('output_guard_enabled')} | num_predict={self.registry.get('llm_num_predict')} | repeat_penalty={self.registry.get('llm_repeat_penalty')} | max_chars={self.registry.get('llm_max_output_chars')}",
            f"Active behavior preset: {self.active_personality_name}",
            f"Active summon: {active_summon.get('name', '')}",
            f"Last reload: {self.registry.get('last_config_reload')}",
            "",
            "Files:",
            f"- {AGENT_CONFIG_PATH}",
            f"- {PROMPTS_CONFIG_PATH}",
            f"- {METADATA_CONFIG_PATH}",
            f"- {PERSONALITIES_CONFIG_PATH}",
        ]
        return "\n".join(lines).rstrip()

    def format_metadata_summary(self) -> str:
        metadata = self.active_metadata()
        lines = [
            "Agent Metadata:",
            f"Name: {metadata.get('agent_name', APP_NAME)}",
            f"Role: {metadata.get('agent_role', '')}",
            f"Version: {metadata.get('version', '')}",
            f"Profile: {metadata.get('profile', '')}",
            f"Active personality: {self.active_personality_name}",
            f"Description: {metadata.get('description', '')}",
        ]
        tags = metadata.get("tags")
        if isinstance(tags, list) and tags:
            lines.append("Tags: " + ", ".join(str(x) for x in tags))
        return "\n".join(lines).rstrip()

    def format_prompts_summary(self) -> str:
        prompts = self.prompts if isinstance(self.prompts, dict) else {}
        lines = ["Prompt Config:"]
        for key in [
            "system_prompt",
            "tool_synthesis_prompt",
            "grounded_answer_prompt",
            "contextual_reply_prompt",
        ]:
            value = clean_text(prompts.get(key, ""))
            lines.append(f"{key}: {truncate_text(value, 500)}")
        return "\n\n".join(lines).rstrip()

    def format_decision_summary(self, decision: Optional[Dict[str, Any]] = None) -> str:
        decision = decision if isinstance(decision, dict) else self.registry.get("last_route_decision")
        if not isinstance(decision, dict):
            return "No route decision data is available yet."
        lines = [
            "Last Route Decision:",
            f"Intent: {decision.get('intent', '')}",
            f"Route: {decision.get('route', '')}",
            f"Command: {decision.get('command', '')}",
            f"Confidence: {decision.get('confidence', '')}",
            f"Requires web: {decision.get('requires_web', '')}",
            f"Requires memory: {decision.get('requires_memory', '')}",
            f"Requires LLM response: {decision.get('requires_llm_response', '')}",
            f"Rewritten request: {decision.get('rewritten_user_request', '')}",
        ]
        if decision.get("reasoning_summary"):
            lines.append(f"Reasoning: {decision.get('reasoning_summary')}")
        if decision.get("missing_arguments"):
            lines.append(f"Missing arguments: {', '.join(str(x) for x in decision.get('missing_arguments') or [])}")
        if decision.get("safety_notes"):
            lines.append(f"Safety notes: {', '.join(str(x) for x in decision.get('safety_notes') or [])}")
        if decision.get("args"):
            lines.append("Args:")
            lines.append(as_json_text(decision.get("args")))
        return "\n".join(lines).rstrip()

    def format_plan_summary(self, plan: Optional[Dict[str, Any]] = None) -> str:
        plan = plan if isinstance(plan, dict) else self.registry.get("last_plan")
        if not isinstance(plan, dict):
            return "No plan data is available yet."
        lines = [
            "Last Shared Plan:",
            f"Route: {plan.get('route', '')}",
            f"Command: {plan.get('command', '')}",
            f"Requires LLM response: {plan.get('requires_llm_response', '')}",
            f"Source kind: {plan.get('source_kind', '')}",
            f"Rewritten text: {plan.get('rewritten_text', '')}",
        ]
        if plan.get("args"):
            lines.append("Args:")
            lines.append(as_json_text(plan.get("args")))
        return "\n".join(lines).rstrip()

    def _source_confidence_summary(self, item: Dict[str, Any]) -> str:
        conf = item.get("source_confidence") or {}
        if not isinstance(conf, dict) or not conf:
            return ""
        score = conf.get("score", "")
        accepted = conf.get("accepted", "")
        reasons = conf.get("reasons") or []
        parts = []
        if score != "":
            parts.append(f"Confidence: {score}")
        if accepted != "":
            parts.append(f"Accepted: {accepted}")
        if reasons:
            parts.append("Reasons: " + "; ".join(str(r) for r in reasons[:5]))
        return " | ".join(parts)

    def _format_source_item(self, index: int, item: Dict[str, Any]) -> str:
        title = clean_text(item.get("title") or item.get("name") or "Untitled source")
        url = clean_text(item.get("url") or item.get("requested_url") or "")
        snippet = clean_text(item.get("snippet") or item.get("description") or item.get("text_preview") or "")
        conf = self._source_confidence_summary(item)
        lines = [f"{index}. {title}"]
        if url:
            lines.append(f"   {url}")
        if conf:
            lines.append(f"   {conf}")
        if snippet:
            lines.append(f"   {truncate_text(snippet, 260)}")
        return "\n".join(lines)

    def _collect_last_source_items(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        seen = set()

        def add(item: Optional[Dict[str, Any]]) -> None:
            if not isinstance(item, dict):
                return
            url = clean_text(item.get("url") or item.get("requested_url") or "")
            title = clean_text(item.get("title") or item.get("name") or "")
            key = url or title
            if not key or key in seen:
                return
            seen.add(key)
            items.append(item)

        grounding = self.registry.get("last_grounding")
        if isinstance(grounding, dict):
            multi = grounding.get("multi_source") or {}
            if isinstance(multi, dict):
                for page in multi.get("pages") or []:
                    add(page)
                for cand in multi.get("candidates") or []:
                    add(cand)
            wiki = grounding.get("wikipedia") or {}
            summary = wiki.get("summary") if isinstance(wiki, dict) else None
            if isinstance(summary, dict):
                add({
                    "title": summary.get("title", "Wikipedia"),
                    "url": summary.get("url", ""),
                    "snippet": summary.get("extract", ""),
                    "source_confidence": wiki.get("source_confidence"),
                })
            page = grounding.get("page")
            if isinstance(page, dict):
                add(page)

        search = self.registry.get("last_web_search")
        if isinstance(search, dict):
            for result in search.get("results") or []:
                add(result)

        page = self.registry.get("last_web_page")
        if isinstance(page, dict):
            add(page)
        return items

    def format_last_sources(self) -> str:
        items = self._collect_last_source_items()
        if not items:
            return "No sources are available yet."
        lines = ["Sources from last answer or web action:", ""]
        for i, item in enumerate(items[:20], start=1):
            lines.append(self._format_source_item(i, item))
            lines.append("")
        return "\n".join(lines).rstrip()

    def format_last_grounding(self) -> str:
        grounding = self.registry.get("last_grounding")
        if not isinstance(grounding, dict):
            return "No grounding data is available yet."
        gq = grounding.get("grounding_query") or {}
        if not gq and isinstance(grounding.get("multi_source"), dict):
            gq = grounding.get("multi_source", {}).get("grounding_query") or {}
        lines: List[str] = ["Grounding Query Plan:"]
        if gq:
            lines.append(f"Original: {gq.get('original', '')}")
            lines.append(f"Profile: {gq.get('profile', '')}")
            lines.append(f"Wikipedia query: {gq.get('wikipedia_query', '')}")
            lines.append(f"Web query: {gq.get('web_query', '')}")
            lines.append(f"Required terms: {', '.join(gq.get('required_terms') or [])}")
            lines.append(f"Optional terms: {', '.join(gq.get('optional_terms') or [])}")
            lines.append(f"Preferred domains: {', '.join(gq.get('preferred_domains') or [])}")
        else:
            lines.append("No structured grounding query was recorded.")

        wiki = grounding.get("wikipedia") or {}
        if isinstance(wiki, dict):
            lines.extend(["", "Wikipedia:", f"Status: {wiki.get('ok')}", f"Reason: {wiki.get('reason', '')}"])
            summary = wiki.get("summary") or {}
            if isinstance(summary, dict) and summary:
                lines.append(f"Title: {summary.get('title', '')}")
                lines.append(f"URL: {summary.get('url', '')}")
                extract = clean_text(summary.get("extract") or wiki.get("extract") or "")
                if extract:
                    lines.append(f"Extract: {truncate_text(extract, 500)}")
            elif summary:
                lines.append(f"Title: {wiki.get('title', '')}")
                lines.append(f"URL: {wiki.get('url', '')}")
                lines.append(f"Extract: {truncate_text(clean_text(summary), 500)}")
            conf = wiki.get("source_confidence") or {}
            if conf:
                lines.append(f"Confidence: {conf.get('score', '')} | Accepted: {conf.get('accepted', '')}")

        multi = grounding.get("multi_source") or {}
        if isinstance(multi, dict):
            accepted = multi.get("candidates") or []
            rejected = multi.get("rejected_candidates") or []
            pages = multi.get("pages") or []
            lines.extend(["", f"Multi-source profile: {multi.get('profile', '')}", f"Fetched pages: {len(pages)}", f"Accepted candidates: {len(accepted)}", f"Weak/rejected candidates: {len(rejected)}"])
            if accepted:
                lines.extend(["", "Accepted Sources:"])
                for i, item in enumerate(accepted[:10], start=1):
                    lines.append(self._format_source_item(i, item))
            if pages:
                lines.extend(["", "Fetched Sources:"])
                for i, page in enumerate(pages[:10], start=1):
                    lines.append(self._format_source_item(i, page))
            if rejected:
                lines.extend(["", "Weak / Rejected Sources:"])
                for i, item in enumerate(rejected[:8], start=1):
                    lines.append(self._format_source_item(i, item))
            errors = multi.get("errors") or []
            if errors:
                lines.extend(["", "Source collection errors:"])
                for err in errors:
                    lines.append(f"- {err}")
        return "\n".join(lines).rstrip()

    def format_last_compact(self) -> str:
        plan = self.registry.get("last_plan") if isinstance(self.registry.get("last_plan"), dict) else {}
        result = self.registry.get("last_result") if isinstance(self.registry.get("last_result"), dict) else {}
        page = self.registry.get("last_web_page") if isinstance(self.registry.get("last_web_page"), dict) else {}
        grounding = self.registry.get("last_grounding") if isinstance(self.registry.get("last_grounding"), dict) else {}
        multi = grounding.get("multi_source") if isinstance(grounding.get("multi_source"), dict) else {}
        lines = ["Last Command:", f"Command: {plan.get('command', '')}", f"Route: {plan.get('route', '')}", f"OK: {result.get('ok', '')}", f"Handled: {result.get('handled', '')}", f"Message: {result.get('message', '')}"]
        if page:
            lines.extend(["", "Last Web Page:", f"Title: {page.get('title', '')}", f"URL: {page.get('url', '')}"])
        if multi:
            lines.extend(["", "Grounding Sources:", f"Fetched pages: {len(multi.get('pages') or [])}", f"Accepted candidates: {len(multi.get('candidates') or [])}", f"Weak/rejected candidates: {len(multi.get('rejected_candidates') or [])}"])
        return "\n".join(lines).rstrip()

    def format_last_plan(self) -> str:
        return self.format_plan_summary(self.registry.get("last_plan"))

    def format_last_json(self) -> str:
        result = self.registry.get("last_result")
        if result is None:
            return "No last_result JSON is available yet."
        return as_json_text(result)

    # --------------------------------------------------------
    # LLM responses
    # --------------------------------------------------------

    def get_llm_temperature(self, purpose: str, default: float = 0.4) -> float:
        p = self.active_personality if isinstance(self.active_personality, dict) else {}
        options = p.get("llm_options") if isinstance(p.get("llm_options"), dict) else {}

        key_map = {
            "chat": "chat_temperature",
            "tool": "tool_temperature",
            "grounded": "grounded_temperature",
            "contextual": "contextual_temperature",
        }

        key = key_map.get(purpose, purpose)
        value = options.get(key, default)

        try:
            temp = float(value)
        except Exception:
            temp = float(default)

        return max(0.0, min(2.0, temp))

    def output_guard_settings(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.registry.get("output_guard_enabled", True)),
            "num_predict": coerce_int(self.registry.get("llm_num_predict"), 768, 64, 8192),
            "repeat_penalty": max(0.8, min(2.0, float(self.registry.get("llm_repeat_penalty", 1.15) or 1.15))),
            "max_output_chars": coerce_int(self.registry.get("llm_max_output_chars"), 12000, 1000, 200000),
            "max_stream_seconds": coerce_int(self.registry.get("llm_max_stream_seconds"), 120, 5, 1800),
            "repeat_tail_chars": coerce_int(self.registry.get("llm_repeat_tail_chars"), 2400, 500, 20000),
            "repeat_min_chars": coerce_int(self.registry.get("llm_repeat_min_chars"), 80, 20, 1000),
            "repeat_threshold": coerce_int(self.registry.get("llm_repeat_threshold"), 3, 2, 10),
        }

    def format_output_guard_status(self) -> str:
        settings = self.output_guard_settings()
        lines = [
            "Output/runaway guard:",
            f"- enabled: {settings['enabled']}",
            f"- Ollama num_predict: {settings['num_predict']}",
            f"- Ollama repeat_penalty: {settings['repeat_penalty']}",
            f"- max output chars: {settings['max_output_chars']}",
            f"- max stream seconds: {settings['max_stream_seconds']}",
            f"- repeated-span threshold: {settings['repeat_threshold']} x >= {settings['repeat_min_chars']} chars",
        ]
        last = self.registry.get("last_output_guard")
        if isinstance(last, dict) and last:
            lines.append("Last guard event:")
            lines.append(as_json_text(last))
        return "\n".join(lines)

    def normalize_for_repeat_guard(self, text: str) -> str:
        text = re.sub(r"\s+", " ", str(text or "")).strip().lower()
        text = re.sub(r"[^a-z0-9 .,;:!?_/#()\-]+", "", text)
        return text

    def detect_repeated_output(self, text: str) -> Optional[str]:
        settings = self.output_guard_settings()
        if not settings["enabled"]:
            return None
        tail = self.normalize_for_repeat_guard(text)[-int(settings["repeat_tail_chars"]):]
        min_chars = int(settings["repeat_min_chars"])
        threshold = int(settings["repeat_threshold"])
        if len(tail) < min_chars * threshold:
            return None

        # Paragraph-level loop detection catches the common failure mode where a model
        # repeats whole blocks.
        paragraphs = [
            self.normalize_for_repeat_guard(p)
            for p in re.split(r"\n\s*\n", text or "")
            if len(self.normalize_for_repeat_guard(p)) >= min_chars
        ]
        if paragraphs:
            recent = paragraphs[-threshold:]
            if len(recent) == threshold and len(set(recent)) == 1:
                return "repeated paragraph"

        # Suffix-span loop detection catches repeated text even without paragraph breaks.
        for span_len in (600, 400, 250, 160, 100, min_chars):
            if span_len < min_chars or len(tail) < span_len * threshold:
                continue
            chunks = [tail[-span_len * i: -span_len * (i - 1) if i > 1 else None] for i in range(threshold, 0, -1)]
            chunks = [c.strip() for c in chunks if c and len(c.strip()) >= min_chars]
            if len(chunks) == threshold and len(set(chunks)) == 1:
                return f"repeated {span_len}-char span"
        return None

    def guard_marker(self, reason: str) -> str:
        return f"\n\n[stopped: output guard — {reason}]"

    def record_output_guard_event(self, reason: str, text: str, *, mode: str) -> Dict[str, Any]:
        event = {
            "reason": reason,
            "mode": mode,
            "chars": len(text or ""),
            "created_at": now_str(),
        }
        self.registry["last_output_guard"] = event
        self.emit("output_guard", event)
        return event

    def apply_output_guard_to_complete_text(self, text: str, *, mode: str = "complete") -> str:
        if not self.output_guard_settings()["enabled"]:
            return text.strip()
        settings = self.output_guard_settings()
        reason = self.detect_repeated_output(text)
        max_chars = int(settings["max_output_chars"])
        if not reason and len(text or "") > max_chars:
            reason = f"max output chars {max_chars}"
            text = (text or "")[:max_chars].rstrip()
        if reason:
            self.record_output_guard_event(reason, text, mode=mode)
            return (text or "").rstrip() + self.guard_marker(reason)
        self.registry["last_output_guard"] = None
        return (text or "").strip()

    def stream_llm_response(self, messages: List[Dict[str, str]]) -> str:
        collected: List[str] = []
        temperature = self.get_llm_temperature("chat", 0.4)
        guard = self.output_guard_settings()
        start = time.monotonic()
        stop_reason: Optional[str] = None
        self.emit("assistant_start", {})
        try:
            for token in self.ollama.chat_stream(
                messages,
                temperature=temperature,
                num_predict=int(guard["num_predict"]),
                repeat_penalty=float(guard["repeat_penalty"]),
            ):
                collected.append(token)
                current = "".join(collected)
                if guard["enabled"]:
                    if len(current) >= int(guard["max_output_chars"]):
                        stop_reason = f"max output chars {guard['max_output_chars']}"
                    elif (time.monotonic() - start) >= int(guard["max_stream_seconds"]):
                        stop_reason = f"max stream seconds {guard['max_stream_seconds']}"
                    else:
                        stop_reason = self.detect_repeated_output(current)
                if stop_reason:
                    current = current[: int(guard["max_output_chars"])].rstrip()
                    marker = self.guard_marker(stop_reason)
                    self.emit("stream_token", {"token": marker})
                    collected = [current, marker]
                    self.record_output_guard_event(stop_reason, current, mode="stream")
                    break
                self.emit("stream_token", {"token": token})
            reply = "".join(collected).strip()
            if not stop_reason:
                self.registry["last_output_guard"] = None
            return reply
        finally:
            self.emit("assistant_done", {"text": "".join(collected).strip(), "guard_reason": stop_reason})

    def complete_llm_response(self, messages: List[Dict[str, str]]) -> str:
        self.emit("assistant_start", {})
        reply = ""
        temperature = self.get_llm_temperature("chat", 0.4)
        guard = self.output_guard_settings()
        try:
            reply = self.ollama.chat_once(
                messages,
                temperature=temperature,
                num_predict=int(guard["num_predict"]),
                repeat_penalty=float(guard["repeat_penalty"]),
            )
            reply = self.apply_output_guard_to_complete_text(reply, mode="complete")
            self.emit("stream_token", {"token": reply})
            return reply
        finally:
            self.emit("assistant_done", {"text": reply})

    def deterministic_contextual_answer(self, user_text: str) -> Optional[str]:
        lowered = clean_text(user_text).lower()
        structured = self.registry.get("last_search_structured")
        if not isinstance(structured, dict):
            structured = {}

        best_title = clean_text(structured.get("best_title") or "")
        best_url = clean_text(structured.get("best_url") or "")
        director = clean_text(structured.get("director") or "")
        cast = clean_text(structured.get("cast") or "")
        docs_url = clean_text(structured.get("docs_url") or "")
        repo_url = clean_text(structured.get("repo_url") or "")
        package_url = clean_text(structured.get("package_url") or "")
        year = clean_text(structured.get("year") or "")
        type_hint = clean_text(structured.get("type_hint") or "")

        label_parts: List[str] = []
        if best_title:
            label_parts.append(best_title)
        if type_hint and type_hint.lower() not in best_title.lower():
            label_parts.append(type_hint)
        if year and year not in " ".join(label_parts):
            label_parts.append(year)
        label = " — ".join(label_parts) if label_parts else "The previous result"

        if re.search(r"\bwho\s+directed\b", lowered):
            if director:
                answer = f"{label} was directed by {director}."
                if best_url:
                    answer += f"\n\nSource:\n{best_url}"
                return answer
            return "The recent context does not contain the director."

        if re.search(r"\b(who\s+starred|who\s+stars|cast|actors?|actresses?)\b", lowered):
            if cast:
                answer = f"The recent search result mentions these cast/people: {cast}."
                if best_url:
                    answer += f"\n\nSource:\n{best_url}"
                return answer
            return "The recent context does not contain cast information."

        if re.search(r"\b(where\s+are\s+the\s+docs|where\s+is\s+the\s+documentation|docs|documentation)\b", lowered):
            if docs_url:
                return f"The documentation is here:\n{docs_url}"
            return "The recent context does not contain a documentation URL."

        if re.search(r"\b(where\s+is\s+the\s+repo|where\s+is\s+the\s+repository|repo|repository)\b", lowered):
            if repo_url:
                return f"The repository is here:\n{repo_url}"
            return "The recent context does not contain a repository URL."

        if re.search(
            r"\b("
            r"where\s+is\s+the\s+package|"
            r"where\s+is\s+the\s+pypi(?:\s+page)?|"
            r"package\s+page|"
            r"pypi\s+page|"
            r"where\s+can\s+i\s+install|"
            r"how\s+do\s+i\s+install\s+it|"
            r"install\s+it|"
            r"install\s+page"
            r")\b",
            lowered,
        ):
            if package_url:
                return f"The package page is here:\n{package_url}"
            return "The recent context does not contain a package URL."

        return None

    def contextual_reply(self, user_text: str) -> str:
        deterministic = self.deterministic_contextual_answer(user_text)
        if deterministic:
            self.emit("assistant_start", {})
            self.emit("stream_token", {"token": deterministic})
            self.emit("assistant_done", {"text": deterministic})
            self.remember_exchange(user_text, deterministic)
            return deterministic

        last_search_task = clean_text(self.registry.get("last_search_task") or "")
        last_search_query = clean_text(self.registry.get("last_search_query") or "")
        last_search_answer_profile = clean_text(self.registry.get("last_search_answer_profile") or "")
        last_search_source_hint = clean_text(self.registry.get("last_search_source_hint") or "")
        last_search_fact_hints = clean_text(self.registry.get("last_search_fact_hints") or "")
        last_search_context = str(self.registry.get("last_search_context") or "")
        last_search_structured = self.registry.get("last_search_structured") if isinstance(self.registry.get("last_search_structured"), dict) else {}

        last_page = self.registry.get("last_web_page") if isinstance(self.registry.get("last_web_page"), dict) else {}
        last_summary = self.registry.get("last_web_summary") if isinstance(self.registry.get("last_web_summary"), dict) else {}

        if not last_search_context and not last_page and not last_summary and not self.messages:
            response = "I do not have enough recent context to know what that refers to."
            self.emit_text("context", response)
            self.remember_exchange(user_text, response)
            return response

        context = f"""
    RECENT CONTEXT POLICY
    Answer the user's follow-up using recent context.
    Resolve pronouns like "it", "that", "this", "the film", "the page", "the repo", or "the docs" from the context below.
    If the context contains the answer, answer directly in the first sentence.
    If the context does not contain the answer, say the recent context does not contain that information.
    Do not invent facts.

    USER FOLLOW-UP:
    {user_text}

    LAST SEARCH TASK:
    {last_search_task}

    LAST SEARCH QUERY:
    {last_search_query}

    LAST SEARCH ANSWER PROFILE:
    {last_search_answer_profile}

    LAST SEARCH SOURCE HINT:
    {last_search_source_hint}

    LAST SEARCH FACT HINTS:
    {last_search_fact_hints}

    LAST SEARCH STRUCTURED CONTEXT:
    {as_json_text(last_search_structured)}

    LAST SEARCH CONTEXT:
    {truncate_text(last_search_context, 10000)}

    LAST WEB PAGE:
    Title: {last_page.get("title", "") if last_page else ""}
    URL: {last_page.get("url", "") if last_page else ""}
    Preview: {truncate_text(last_page.get("text_preview", ""), 1500) if last_page else ""}

    LAST WEB SUMMARY:
    {truncate_text(as_json_text(last_summary), 3000) if last_summary else ""}

    RECENT CHAT:
    {as_json_text(self.messages[-MAX_CHAT_CONTEXT_MESSAGES:])}
    """.strip()

        contextual_prompt = self.build_effective_system_prompt(
            "contextual_reply_prefix",
            self.prompts.get("contextual_reply_prompt") if isinstance(self.prompts, dict) else "",
        )
        messages = [
            {
                "role": "system",
                "content": contextual_prompt + "\n\n" + (
                    "Resolve references like it/that/the film/the repo/the docs from recent context. "
                    "If the answer is present, answer directly. "
                    "If not present, say the recent context does not contain the answer. "
                    "Do not perform a new unsupported factual guess."
                ),
            },
            {"role": "user", "content": context},
        ]

        reply = self.stream_llm_response(messages) if self.registry.get("streaming_enabled", True) else self.complete_llm_response(messages)
        self.remember_exchange(user_text, reply)
        return reply

    def raw_prompt_reply(self, user_text: str) -> str:
        messages = [{"role": "user", "content": user_text}]
        reply = self.stream_llm_response(messages) if self.registry.get("streaming_enabled", True) else self.complete_llm_response(messages)
        self.remember_exchange(user_text, reply)
        return reply

    def summon_prompt_reply(self, user_text: str) -> str:
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.build_effective_system_prompt("summon_prompt_prefix")}
        ]
        messages.extend(self.messages[-MAX_CHAT_CONTEXT_MESSAGES:])
        messages.append({"role": "user", "content": user_text})
        reply = self.stream_llm_response(messages) if self.registry.get("streaming_enabled", True) else self.complete_llm_response(messages)
        self.remember_exchange(user_text, reply)
        return reply

    def chat_reply(self, user_text: str, extra_context: Optional[str] = None) -> str:
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.build_effective_system_prompt("chat_prefix")}
        ]
        if extra_context:
            messages.append({"role": "system", "content": f"Context for this response:\n{extra_context}"})
        messages.extend(self.messages[-MAX_CHAT_CONTEXT_MESSAGES:])
        messages.append({"role": "user", "content": user_text})
        reply = self.stream_llm_response(messages) if self.registry.get("streaming_enabled", True) else self.complete_llm_response(messages)
        self.remember_exchange(user_text, reply)
        return reply

    def synthesize_tool_response(self, *, user_text: str, tool_name: str, tool_context: str, instruction: str = "") -> str:
        tool_prompt = self.build_effective_system_prompt(
            "tool_synthesis_prefix",
            self.prompts.get("tool_synthesis_prompt") if isinstance(self.prompts, dict) else "",
        )
        messages = [
            {
                "role": "system",
                "content": (
                    tool_prompt + "\n\n" +
                    "Hard evidence rule: personality may affect tone and formatting, but tool answers must use only tool evidence. "
                    "Your task is to answer the user's ORIGINAL REQUEST, not summarize the tool output. "
                    "Treat the tool output as evidence. "
                    "First decide what the user is asking for: a fact, a source, a how-to answer, "
                    "a comparison, a list, a recommendation, or a lookup. Then answer that request directly. "
                    "Use only evidence present in the tool context. "
                    "Do not output JSON. Do not dump raw search results. "
                    "Never reveal or copy internal prompt headings such as USER TASK, TOOL EVIDENCE, ANSWERING RULE, SEARCH QUERY USED, ANSWER PROFILE, or RESPONSE FORMAT HINT. "
                    "If the answer is present, give the answer in the first sentence. "
                    "Do not stop after identifying a URL. If the evidence contains facts such as director, "
                    "cast, date, version, author, repository, package name, installation hint, or documentation purpose, "
                    "include those facts in the answer. "
                    "If the tool evidence includes extracted fact hints, use them. "
                    "If the user asked to find a page/source, identify the best page/source first and explain why it is the best match. "
                    "If the user asked for documentation, point to the most relevant official/docs source first and what it is useful for. "
                    "If only partial evidence is present, say what can be answered and what is uncertain. "
                    "Include source URLs after the answer when URLs are available. "
                    "Never invent facts that are not supported by the tool evidence."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"USER ORIGINAL REQUEST:\n{user_text}\n\n"
                    f"TOOL USED:\n{tool_name}\n\n"
                    "ANSWERING RULE:\n"
                    "Answer the USER ORIGINAL REQUEST directly. "
                    "The tool output below is evidence, not the final answer. "
                    "Do not merely summarize the evidence list. "
                    "Use extracted fact hints when present.\n\n"
                    f"TOOL EVIDENCE:\n{tool_context}\n\n"
                    f"SPECIFIC INSTRUCTION:\n{instruction or 'Answer the original request directly using the evidence.'}"
                ),
            },
        ]
        reply = self.stream_llm_response(messages) if self.registry.get("streaming_enabled", True) else self.complete_llm_response(messages)
        reply = clean_internal_prompt_leak(reply)
        self.remember_exchange(user_text, reply)
        return reply

    def summarize_web_page(self, page: Dict[str, Any], *, query: Optional[str] = None, search_results: Optional[List[Dict[str, Any]]] = None, remember_history: bool = True) -> str:
        source_lines = [f"{i}. {r.get('title')} — {r.get('url')}" for i, r in enumerate(search_results or [])]
        context = f"""
WEB PAGE
Title: {page.get('title') or ''}
URL: {page.get('url') or ''}
Query: {query or ''}

Search results:
{chr(10).join(source_lines)}

Extracted page text:
{truncate_text(page.get('text') or '', MAX_WEB_TEXT_CHARS)}
""".strip()
        messages = [
            {
                "role": "system",
                "content": (
                    self.build_effective_system_prompt(
                        "tool_synthesis_prefix",
                        self.prompts.get("tool_synthesis_prompt") if isinstance(self.prompts, dict) else "",
                    )
                    + "\n\nSummarize the extracted web page text. Include the main point, key details, useful references, and caveats if the text appears incomplete. Do not claim content that is not present. Stay in the active summon voice if a summon is active."
                ),
            },
            {"role": "user", "content": context},
        ]
        reply = self.stream_llm_response(messages) if self.registry.get("streaming_enabled", True) else self.complete_llm_response(messages)
        if remember_history:
            title_or_url = page.get("title") or page.get("url") or "web page"
            history_prompt = f"Summarize web page: {title_or_url}"
            if query:
                history_prompt = f"Summarize web page for query '{query}': {title_or_url}"
            self.remember_exchange(history_prompt, reply)
        return reply

    # --------------------------------------------------------
    # Grounding
    # --------------------------------------------------------

    def collect_multi_source_grounding(self, query: Any) -> Dict[str, Any]:
        if isinstance(query, GroundingQuery):
            grounding_query = query
        else:
            grounding_query = build_grounding_query(str(query))
        profile = grounding_query.profile
        domains = list(grounding_query.preferred_domains or GROUNDING_SOURCE_PROFILES.get(profile, []))
        web_query = clean_text(grounding_query.web_query or grounding_query.original)
        allow_private = bool(self.registry.get("allow_private_url_fetch", False))
        searches: List[Dict[str, Any]] = []
        candidates: List[Dict[str, Any]] = []
        fetched_pages: List[Dict[str, Any]] = []
        page_confidence: List[Dict[str, Any]] = []
        errors: List[str] = []
        self.emit("ground", {"message": f"Query profile: {profile}"})
        self.emit("ground", {"message": f"Wikipedia query: {grounding_query.wikipedia_query}"})
        self.emit("ground", {"message": f"Web query: {web_query}"})
        try:
            self.emit("ground", {"message": f"Searching general web: {web_query}"})
            general = self.web.search(web_query, max_results=MAX_SEARCH_RESULTS)
            searches.append(general)
            candidates.extend(general.get("results", []) or [])
        except Exception as exc:
            errors.append(f"general web search failed: {exc}")
        for domain in domains:
            try:
                self.emit("ground", {"message": f"Searching {domain}: {web_query}"})
                result = self.web.search(web_query, max_results=GROUNDING_MAX_SEARCH_RESULTS_PER_SOURCE, site=domain)
                searches.append(result)
                candidates.extend(result.get("results", []) or [])
            except Exception as exc:
                errors.append(f"{domain} search failed: {exc}")
        candidates = dedupe_result_items(candidates)
        accepted_candidates, rejected_candidates = filter_candidates_by_confidence(candidates, grounding_query)
        fetch_pool = accepted_candidates or rejected_candidates[:GROUNDING_MAX_FETCHED_SOURCES]
        fetch_pool.sort(key=lambda item: source_priority_score(item.get("url", "")))
        for item in fetch_pool[:GROUNDING_MAX_FETCHED_SOURCES]:
            url = item.get("url", "")
            if not url:
                continue
            try:
                self.emit("ground", {"message": f"Fetching source: {item.get('title')} — {url}"})
                page = self.web.fetch(url, allow_private=allow_private)
                confidence = score_source_against_query(item, grounding_query, page.get("text", ""))
                page["source_confidence"] = confidence.to_dict()
                page_confidence.append(confidence.to_dict())
                fetched_pages.append(page)
                self.registry["last_web_page"] = page
                if confidence.accepted:
                    self.emit("ground", {"message": f"Accepted source: {page.get('title') or item.get('title')}"})
                else:
                    self.emit("ground", {"message": f"Weak source: {page.get('title') or item.get('title')}"})
            except Exception as exc:
                fetched_pages.append({"fetch_error": str(exc), "url": url, "title": item.get("title", ""), "text": "", "source_confidence": item.get("source_confidence")})
        payload = {
            "profile": profile,
            "query": web_query,
            "grounding_query": grounding_query.to_dict(),
            "domains": domains,
            "searches": searches,
            "candidates": accepted_candidates[:20],
            "rejected_candidates": rejected_candidates[:20],
            "pages": fetched_pages,
            "page_confidence": page_confidence,
            "errors": errors,
        }
        if searches:
            self.registry["last_web_search"] = searches[0]
        return payload

    def build_grounding_answer_context(
        self,
        *,
        user_text: str,
        wikipedia_data: Optional[Dict[str, Any]] = None,
        web_data: Optional[Dict[str, Any]] = None,
        fetched_page: Optional[Dict[str, Any]] = None,
        multi_source_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Compact source pack for the final answer prompt.

        The verbose debug grounding context is still available through /grounding,
        but the LLM answer prompt gets a simpler source pack so it does not
        reproduce internal policy/tool headings in the final response.
        """
        source_lines: List[str] = []

        def add_source(title: str, url: str, text: str, limit: int = 1600) -> None:
            title = clean_text(title or "Untitled source")
            url = clean_text(url or "")
            body = clean_text(text or "")
            if not body and not url:
                return
            idx = len(source_lines) + 1
            note = f"{idx}. {title}"
            if url:
                note += f"\nURL: {url}"
            if body:
                note += f"\nRelevant text: {truncate_text(body, limit)}"
            source_lines.append(note)

        if wikipedia_data and wikipedia_data.get("ok"):
            summary = wikipedia_data.get("summary") or {}
            if isinstance(summary, dict):
                add_source(summary.get("title") or wikipedia_data.get("title") or "Wikipedia", summary.get("url") or wikipedia_data.get("url") or "", summary.get("extract") or wikipedia_data.get("extract") or "", 1800)
            else:
                add_source(wikipedia_data.get("title") or "Wikipedia", wikipedia_data.get("url") or "", clean_text(summary) or wikipedia_data.get("extract") or "", 1800)

        if fetched_page and not fetched_page.get("fetch_error"):
            conf = fetched_page.get("source_confidence") or {}
            if conf.get("accepted", True):
                add_source(fetched_page.get("title", "Fetched source"), fetched_page.get("url", ""), fetched_page.get("text", ""), 2200)

        if isinstance(multi_source_data, dict):
            for page in multi_source_data.get("pages") or []:
                if len(source_lines) >= 5:
                    break
                if not page or page.get("fetch_error"):
                    continue
                conf = page.get("source_confidence") or {}
                if not conf.get("accepted", True):
                    continue
                add_source(page.get("title", "Fetched source"), page.get("url", ""), page.get("text", ""), 2200)

            if len(source_lines) < 3:
                for item in multi_source_data.get("candidates") or []:
                    if len(source_lines) >= 5:
                        break
                    conf = item.get("source_confidence") or {}
                    if conf and not conf.get("accepted", True):
                        continue
                    add_source(item.get("title", "Search result"), item.get("url", ""), item.get("snippet", ""), 900)

        if web_data and len(source_lines) < 3:
            for item in web_data.get("results", [])[:5]:
                if len(source_lines) >= 5:
                    break
                add_source(item.get("title", "Search result"), item.get("url", ""), item.get("snippet", ""), 900)

        if not source_lines:
            source_lines.append("No reliable source text was collected.")

        return (
            "Question to answer:\n"
            f"{user_text}\n\n"
            "Sources you may use:\n"
            f"{chr(10).join(source_lines)}\n\n"
            "Return only the final answer. Do not print these prompt headings. "
            "Do not mention internal rules or source-pack labels."
        )

    def build_grounding_context(
        self,
        *,
        user_text: str,
        wikipedia_data: Optional[Dict[str, Any]] = None,
        web_data: Optional[Dict[str, Any]] = None,
        fetched_page: Optional[Dict[str, Any]] = None,
        multi_source_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        lines = ["GROUNDING POLICY", "Use only the sources below.", "If the sources do not answer the user, say you do not know.", "Do not fill gaps from model memory.", "", f"USER REQUEST: {user_text}", ""]
        grounding_query = multi_source_data.get("grounding_query") if isinstance(multi_source_data, dict) else None
        if grounding_query:
            lines.extend([
                "GROUNDING QUERY PLAN",
                f"Original: {grounding_query.get('original', '')}",
                f"Profile: {grounding_query.get('profile', '')}",
                f"Wikipedia query: {grounding_query.get('wikipedia_query', '')}",
                f"Web query: {grounding_query.get('web_query', '')}",
                f"Required terms: {', '.join(grounding_query.get('required_terms') or [])}",
                f"Optional terms: {', '.join(grounding_query.get('optional_terms') or [])}",
                f"Preferred domains: {', '.join(grounding_query.get('preferred_domains') or [])}",
                "",
            ])
        if wikipedia_data:
            lines += ["WIKIPEDIA GROUNDING", f"Status: {wikipedia_data.get('ok')}", f"Reason: {wikipedia_data.get('reason', '')}"]
            summary = wikipedia_data.get("summary") or {}
            if summary:
                lines += [f"Title: {summary.get('title', '')}", f"Description: {summary.get('description', '')}", f"URL: {summary.get('url', '')}", f"Extract: {summary.get('extract', '')}"]
            search = wikipedia_data.get("search") or {}
            if search.get("results"):
                lines.append("\nWikipedia search candidates:")
                for item in search.get("results", [])[:5]:
                    lines.append(f"{item.get('index', '')}. {item.get('title', '')}\nURL: {item.get('url', '')}\nSnippet: {item.get('snippet', '')}")
            lines.append("")
        if web_data:
            lines += ["WEB SEARCH FALLBACK", f"Query: {web_data.get('query', '')}"]
            for item in web_data.get("results", []):
                lines.append(f"{item.get('index', '')}. {item.get('title', '')}\nURL: {item.get('url', '')}\nSnippet: {item.get('snippet', '')}")
            lines.append("")
        if fetched_page:
            lines += ["FETCHED WEB PAGE", f"Title: {fetched_page.get('title', '')}", f"URL: {fetched_page.get('url', '')}"]
            if fetched_page.get("fetch_error"):
                lines.append(f"Fetch error: {fetched_page.get('fetch_error')}")
            else:
                lines += ["Extracted text:", truncate_text(fetched_page.get("text", ""), 12000)]
            lines.append("")
        if multi_source_data:
            lines.append("MULTI-SOURCE GROUNDING")
            lines.append(f"Profile: {multi_source_data.get('profile', '')}")
            lines.append(f"Query: {multi_source_data.get('query', '')}")
            lines.append("")
            candidates = multi_source_data.get("candidates") or []
            if candidates:
                lines.append("Accepted search candidates:")
                for item in candidates[:12]:
                    conf = item.get("source_confidence") or {}
                    lines.append(f"{item.get('index', '')}. {item.get('title', '')}\nURL: {item.get('url', '')}\nSnippet: {item.get('snippet', '')}\nConfidence: {conf.get('score', '')} | {', '.join(conf.get('reasons') or [])}")
                lines.append("")
            rejected = multi_source_data.get("rejected_candidates") or []
            if rejected:
                lines.append("Rejected or weak search candidates:")
                for item in rejected[:8]:
                    conf = item.get("source_confidence") or {}
                    lines.append(f"{item.get('title', '')}\nURL: {item.get('url', '')}\nConfidence: {conf.get('score', '')} | {', '.join(conf.get('reasons') or [])}")
                lines.append("")
            pages = multi_source_data.get("pages") or []
            for i, page in enumerate(pages):
                conf = page.get("source_confidence") or {}
                lines.append(f"{'WEAK ' if conf.get('accepted') is False else ''}FETCHED SOURCE {i + 1}")
                lines.append(f"Title: {page.get('title', '')}")
                lines.append(f"URL: {page.get('url', '')}")
                if conf:
                    lines.append(f"Confidence: {conf.get('score', '')} | {', '.join(conf.get('reasons') or [])}")
                if page.get("fetch_error"):
                    lines.append(f"Fetch error: {page.get('fetch_error')}")
                else:
                    lines.append("Extracted text:")
                    lines.append(truncate_text(page.get("text", ""), 10000))
                lines.append("")
            errors = multi_source_data.get("errors") or []
            if errors:
                lines.append("Source collection errors:")
                for err in errors:
                    lines.append(f"- {err}")
                lines.append("")
        return "\n".join(lines)


    def _target_summary_from_payload(self, target: str, payload: Dict[str, Any]) -> str:
        lines: List[str] = [f"Target: {target}"]
        wiki = payload.get("wikipedia") if isinstance(payload.get("wikipedia"), dict) else None
        if wiki and wiki.get("ok"):
            summary_value = wiki.get("summary")
            if isinstance(summary_value, dict):
                title = clean_text(wiki.get("title") or summary_value.get("title") or target)
                url = clean_text(wiki.get("url") or summary_value.get("url") or "")
                summary = clean_text(summary_value.get("extract") or summary_value.get("summary") or wiki.get("extract") or "")
            else:
                title = clean_text(wiki.get("title") or target)
                url = clean_text(wiki.get("url") or "")
                summary = clean_text(summary_value or wiki.get("extract") or "")
            lines.append(f"Wikipedia title: {title}")
            if url:
                lines.append(f"URL: {url}")
            if summary:
                lines.append(f"Summary: {truncate_text(summary, 1800)}")
            return "\n".join(lines)

        page = payload.get("page") if isinstance(payload.get("page"), dict) else None
        if page and not page.get("fetch_error"):
            title = clean_text(page.get("title") or target)
            url = clean_text(page.get("url") or "")
            text = clean_text(page.get("text") or "")
            lines.append(f"Fetched page title: {title}")
            if url:
                lines.append(f"URL: {url}")
            if text:
                lines.append(f"Extracted text: {truncate_text(text, 1800)}")
            return "\n".join(lines)

        multi = payload.get("multi_source") if isinstance(payload.get("multi_source"), dict) else None
        if multi:
            for item in multi.get("pages") or []:
                if isinstance(item, dict) and not item.get("fetch_error") and has_grounding_text(item.get("text", "")):
                    title = clean_text(item.get("title") or target)
                    url = clean_text(item.get("url") or "")
                    text = clean_text(item.get("text") or "")
                    lines.append(f"Fetched page title: {title}")
                    if url:
                        lines.append(f"URL: {url}")
                    if text:
                        lines.append(f"Extracted text: {truncate_text(text, 1800)}")
                    return "\n".join(lines)

        response = clean_text(payload.get("response") or "")
        if response:
            lines.append(f"Status: {response}")
        return "\n".join(lines)

    def _format_conjunction_grounding_payload(self, payload: Dict[str, Any]) -> str:
        multi = payload.get("multi_source") if isinstance(payload.get("multi_source"), dict) else {}
        targets = multi.get("conjunction_targets") or []
        children = multi.get("target_payloads") or []
        lines: List[str] = [
            "Grounding Query Plan:",
            f"Original: {(payload.get('grounding_query') or {}).get('original', '')}",
            "Profile: multi_target_reference",
            f"Targets: {', '.join(str(target) for target in targets)}",
            "",
        ]
        for target, child in zip(targets, children):
            wiki = child.get("wikipedia") if isinstance(child, dict) and isinstance(child.get("wikipedia"), dict) else {}
            lines.append(f"Target: {target}")
            lines.append(f"Status: {bool(child.get('ok')) if isinstance(child, dict) else False}")
            if wiki:
                lines.append(f"Wikipedia: {bool(wiki.get('ok'))}")
                wiki_summary = wiki.get("summary") if isinstance(wiki.get("summary"), dict) else {}
                title = clean_text(wiki.get("title") or wiki_summary.get("title") or "")
                url = clean_text(wiki.get("url") or wiki_summary.get("url") or "")
                if title:
                    lines.append(f"Title: {title}")
                if url:
                    lines.append(f"URL: {url}")
            lines.append("")
        return "\n".join(lines).rstrip()

    def _collect_conjunction_grounding_payload(
        self,
        *,
        user_text: str,
        grounding_query: GroundingQuery,
        targets: List[str],
        guard,
        allow_web_fallback: bool,
        emit_progress: bool,
    ) -> Dict[str, Any]:
        child_payloads: List[Dict[str, Any]] = []
        summaries: List[str] = []
        pages: List[Dict[str, Any]] = []
        searches: List[Dict[str, Any]] = []
        candidates: List[Dict[str, Any]] = []

        for target in targets:
            if emit_progress:
                self.emit("ground", {"message": f"Checking target: {target}"})
            child = self._collect_grounding_payload(
                user_text=target,
                query=target,
                allow_web_fallback=allow_web_fallback,
                emit_progress=False,
            )
            child_payloads.append(child)
            summaries.append(self._target_summary_from_payload(target, child))

            page = child.get("page") if isinstance(child.get("page"), dict) else None
            if page:
                pages.append(page)
            web = child.get("web") if isinstance(child.get("web"), dict) else None
            if web:
                searches.append(web)
                candidates.extend([item for item in (web.get("results") or []) if isinstance(item, dict)])
            multi = child.get("multi_source") if isinstance(child.get("multi_source"), dict) else None
            if multi:
                pages.extend([item for item in (multi.get("pages") or []) if isinstance(item, dict)])
                searches.extend([item for item in (multi.get("searches") or []) if isinstance(item, dict)])
                candidates.extend([item for item in (multi.get("candidates") or []) if isinstance(item, dict)])

        strong_grounding = bool(child_payloads) and all(bool(child.get("strong_grounding")) for child in child_payloads)
        weak_grounding = any(bool(child.get("weak_grounding")) for child in child_payloads)
        ok = bool(child_payloads) and all(bool(child.get("ok")) for child in child_payloads)

        combined_summary = "\n\n".join(summary for summary in summaries if clean_text(summary))
        combined_title = "; ".join(targets)
        combined_wiki_summary = {
            "title": combined_title,
            "url": "",
            "extract": combined_summary,
        }
        combined_wiki = {
            "ok": ok,
            "source": "wikipedia:multi_target",
            "query": clean_text(grounding_query.wikipedia_query or grounding_query.original),
            "title": combined_title,
            "url": "",
            "summary": combined_wiki_summary,
            "extract": combined_summary,
            "targets": targets,
        }
        combined_multi = {
            "conjunction_targets": targets,
            "target_payloads": child_payloads,
            "pages": pages,
            "searches": searches,
            "candidates": candidates[:20],
            "errors": [child for child in child_payloads if not child.get("ok")],
        }
        payload = {
            "ok": ok,
            "response": "",
            "grounding_guard": guard.to_dict(),
            "grounding_query": grounding_query.to_dict(),
            "wikipedia": combined_wiki if combined_summary else None,
            "web": searches[0] if searches else None,
            "page": pages[0] if pages else None,
            "multi_source": combined_multi,
            "strong_grounding": strong_grounding,
            "weak_grounding": weak_grounding,
        }

        if not ok:
            grounded = [target for target, child in zip(targets, child_payloads) if child.get("ok")]
            missing = [target for target, child in zip(targets, child_payloads) if not child.get("ok")]
            if grounded and missing:
                response = f"I found grounding for {', '.join(grounded)}, but not for {', '.join(missing)}."
            else:
                response = GROUNDING_WEAK_SOURCE_MESSAGE if weak_grounding else GROUNDING_NO_SOURCE_MESSAGE
            payload["response"] = response
            if emit_progress:
                self.emit_text("ground", response)
            self.registry["last_grounding"] = payload
            return payload

        response = self._format_conjunction_grounding_payload(payload)
        payload["response"] = response
        self.registry["last_grounding"] = payload
        if emit_progress:
            self.emit_text("ground", response)
        return payload

    def _collect_grounding_payload(
        self,
        *,
        user_text: str,
        query: Optional[str] = None,
        allow_web_fallback: bool = True,
        emit_progress: bool = True,
    ) -> Dict[str, Any]:
        grounding_query = build_grounding_query(query or user_text)
        guard = evaluate_grounding_request(user_text or query or grounding_query.original)
        if not guard.allowed:
            response = guard.refusal
            if emit_progress:
                self.emit_text("ground", response)
            payload = {
                "ok": False,
                "response": response,
                "grounding_guard": guard.to_dict(),
                "grounding_query": grounding_query.to_dict(),
                "wikipedia": None,
                "web": None,
                "page": None,
                "multi_source": None,
                "strong_grounding": False,
                "weak_grounding": False,
            }
            self.registry["last_grounding"] = payload
            return payload

        ambiguity_reason = grounding_ambiguity_reason(user_text or query or grounding_query.original, grounding_query)
        if ambiguity_reason:
            response = ambiguity_reason
            if emit_progress:
                self.emit_text("ground", response)
            payload = {
                "ok": False,
                "response": response,
                "grounding_guard": guard.to_dict(),
                "grounding_query": grounding_query.to_dict(),
                "wikipedia": None,
                "web": None,
                "page": None,
                "multi_source": None,
                "strong_grounding": False,
                "weak_grounding": False,
            }
            self.registry["last_grounding"] = payload
            return payload

        conjunction_targets = grounding_conjunction_targets(user_text or query or grounding_query.original, grounding_query)
        if conjunction_targets:
            return self._collect_conjunction_grounding_payload(
                user_text=user_text,
                grounding_query=grounding_query,
                targets=conjunction_targets,
                guard=guard,
                allow_web_fallback=allow_web_fallback,
                emit_progress=emit_progress,
            )

        query_text = clean_text(grounding_query.wikipedia_query or grounding_query.original)
        if emit_progress:
            self.emit("ground", {"message": f"Query profile: {grounding_query.profile}"})
            self.emit("ground", {"message": f"Checking Wikipedia: {query_text}"})
        try:
            wiki_data = self.web.wikipedia_grounding(query_text)
        except Exception as exc:
            wiki_data = {"ok": False, "source": "wikipedia", "query": query_text, "reason": f"Wikipedia lookup failed: {exc}", "search": None, "summary": None}
        if wiki_data.get("ok") and wiki_data.get("summary"):
            summary = wiki_data.get("summary") or {}
            wiki_item = {"url": summary.get("url", ""), "title": summary.get("title", ""), "snippet": summary.get("extract", "")}
            wiki_conf = score_source_against_query(wiki_item, grounding_query, summary.get("extract", ""))
            wiki_data["source_confidence"] = wiki_conf.to_dict()
            if not wiki_conf.accepted:
                wiki_data["ok"] = False
                wiki_data["reason"] = f"Wikipedia match was weak: score={wiki_conf.score}"
        web_data = None
        fetched_page = None
        multi_source_data = None
        should_run_multisource = bool(allow_web_fallback and (not wiki_data.get("ok") or self.registry.get("grounding_always_multisource", False)))
        if should_run_multisource:
            try:
                multi_source_data = self.collect_multi_source_grounding(grounding_query)
                searches = multi_source_data.get("searches") or []
                if searches:
                    web_data = searches[0]
                pages = multi_source_data.get("pages") or []
                if pages:
                    fetched_page = pages[0]
            except Exception as exc:
                web_data = {"ok": False, "query": grounding_query.web_query, "reason": f"Multi-source grounding failed: {exc}", "results": []}
        has_wiki = bool(wiki_data.get("ok"))
        has_fetched_web = bool(fetched_page and not fetched_page.get("fetch_error") and has_grounding_text(fetched_page.get("text", "")) and (fetched_page.get("source_confidence") or {}).get("accepted", True))
        has_search_snippets = bool(has_grounding_text(compact_search_snippets(web_data), min_chars=80))
        has_multi_source_page = False
        has_multi_source_snippets = False
        if isinstance(multi_source_data, dict):
            pages = multi_source_data.get("pages") or []
            has_multi_source_page = any(bool(page and not page.get("fetch_error") and has_grounding_text(page.get("text", "")) and (page.get("source_confidence") or {}).get("accepted", True)) for page in pages)
            has_multi_source_snippets = has_grounding_text(source_result_context(multi_source_data.get("candidates") or [], limit=10), min_chars=80)
        strong_grounding = bool(has_wiki or has_fetched_web or has_multi_source_page)
        weak_grounding = bool(has_search_snippets or has_multi_source_snippets)
        allow_snippet_only = bool(self.registry.get("grounding_allow_snippet_only_answers", False))
        if allow_snippet_only:
            guard = replace(guard, allow_snippet_only=True)
        source_payload = {"wikipedia": wiki_data, "web": web_data, "page": fetched_page, "multi_source": multi_source_data}
        if not grounding_supports_answer(
            guard,
            source_payload,
            strong_grounding=strong_grounding,
            weak_grounding=weak_grounding,
        ):
            response = GROUNDING_WEAK_SOURCE_MESSAGE if weak_grounding else GROUNDING_NO_SOURCE_MESSAGE
            if emit_progress:
                self.emit_text("ground", response)
            payload = {"ok": False, "response": response, "grounding_guard": guard.to_dict(), "grounding_query": grounding_query.to_dict(), "wikipedia": wiki_data, "web": web_data, "page": fetched_page, "multi_source": multi_source_data, "strong_grounding": strong_grounding, "weak_grounding": weak_grounding}
            self.registry["last_grounding"] = payload
            return payload

        payload = {"ok": True, "response": "", "grounding_guard": guard.to_dict(), "grounding_query": grounding_query.to_dict(), "wikipedia": wiki_data, "web": web_data, "page": fetched_page, "multi_source": multi_source_data, "strong_grounding": strong_grounding, "weak_grounding": weak_grounding}
        self.registry["last_grounding"] = payload
        if emit_progress:
            response = self.format_last_grounding()
            payload["response"] = response
            self.emit_text("ground", response)
        return payload

    def grounded_reply(self, *, user_text: str, query: Optional[str] = None, allow_web_fallback: bool = True) -> Dict[str, Any]:
        return self.grounded_llm_reply(
            user_text=user_text,
            query=query,
            allow_web_fallback=allow_web_fallback,
        )

    def grounded_llm_reply(self, *, user_text: str, query: Optional[str] = None, allow_web_fallback: bool = True) -> Dict[str, Any]:
        payload = self._collect_grounding_payload(
            user_text=user_text,
            query=query,
            allow_web_fallback=allow_web_fallback,
            emit_progress=False,
        )
        if not payload.get("ok"):
            self.emit_text("ground", str(payload.get("response") or GROUNDING_NO_SOURCE_MESSAGE))
            return payload

        answer_context = self.build_grounding_answer_context(
            user_text=user_text,
            wikipedia_data=payload.get("wikipedia") if isinstance(payload.get("wikipedia"), dict) else None,
            web_data=payload.get("web") if isinstance(payload.get("web"), dict) else None,
            fetched_page=payload.get("page") if isinstance(payload.get("page"), dict) else None,
            multi_source_data=payload.get("multi_source") if isinstance(payload.get("multi_source"), dict) else None,
        )
        reply = self.synthesize_tool_response(
            user_text=user_text,
            tool_name="grounding.answer",
            tool_context=answer_context,
            instruction=(
                "Answer the user's question directly using only the grounded evidence. "
                "Do not mention internal policy or source-pack labels. "
                "If the evidence is insufficient, say you do not know."
            ),
        )
        reply = clean_internal_prompt_leak(reply)
        payload["response"] = reply
        payload["answer"] = reply
        self.registry["last_grounded_answer"] = payload
        return payload

    # --------------------------------------------------------
    # Main entry
    # --------------------------------------------------------

    def route_input(self, text: str, source_kind: str = "terminal") -> RouteDecision:
        text = str(text or "").strip()
        return self.router.route(text, self.router_context())

    def handle_input(self, text: str, source_kind: str = "terminal") -> DispatchResult:
        text = str(text or "").strip()
        if not text:
            return DispatchResult(True, True, "empty")
        self.emit("user", {"text": text})
        self.registry["command_history"].append({"input": text, "source_kind": source_kind, "at": now_str()})
        self.registry["command_history"] = self.registry["command_history"][-100:]
        try:
            decision = self.route_input(text, source_kind=source_kind)
            self.registry["last_route_decision"] = decision.to_dict()
            self.emit("route", {"decision": decision.to_dict()})
            plan = self.planner.plan(decision, text, source_kind=source_kind)
            result = self.dispatcher.dispatch(plan)
            self.registry["last_result"] = result.to_dict()
            self.emit("done", {"result": result.to_dict()})
            return result
        except Exception as exc:
            result = DispatchResult(False, True, "error", {"error": str(exc)})
            self.registry["last_result"] = result.to_dict()
            self.emit("error", {"error": str(exc)})
            self.emit("done", {"result": result.to_dict()})
            return result


# ============================================================
# PLAIN CONSOLE HOST
# ============================================================

class PlainConsoleEventSink:
    def __init__(self, core_getter: Callable[[], Optional[AgentCore]]) -> None:
        self.core_getter = core_getter
        self.current_assistant_open = False
        self.assistant_token_chars = 0
        self.assistant_stream_had_trailing_newline = False

    def _core(self) -> Optional[AgentCore]:
        try:
            return self.core_getter()
        except Exception:
            return None

    def _raw_json_enabled(self) -> bool:
        core = self._core()
        return bool(core and core.registry.get("raw_tool_json_enabled", False))

    def _begin_assistant(self) -> None:
        if self.current_assistant_open:
            return
        print("\nAssistant>")
        self.current_assistant_open = True
        self.assistant_token_chars = 0
        self.assistant_stream_had_trailing_newline = False

    def _append_token(self, token: str) -> None:
        token = str(token or "")
        if not token:
            return
        self._begin_assistant()
        self.assistant_token_chars += len(token)
        self.assistant_stream_had_trailing_newline = token.endswith("\n")
        print(token, end="", flush=True)

    def _end_assistant(self) -> None:
        if not self.current_assistant_open:
            return
        if self.assistant_token_chars > 0 and not self.assistant_stream_had_trailing_newline:
            print()
        self.current_assistant_open = False
        self.assistant_token_chars = 0
        self.assistant_stream_had_trailing_newline = False

    def emit(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        p = payload or {}
        et = event_type
        if et in {"user", "route", "plan", "status", "done"}:
            return
        if et == "assistant_start":
            self._begin_assistant()
            return
        if et == "stream_token":
            self._append_token(str(p.get("token", "")))
            return
        if et == "assistant_done":
            self._end_assistant()
            return
        if et in {"web", "ground", "memory"}:
            print(f"[{et.upper()}] {p.get('message', '')}")
            return
        if et == "text":
            channel = str(p.get("channel", "info")).upper()
            print(f"\n[{channel}]\n{p.get('text', '')}")
            return
        if et == "json":
            if self._raw_json_enabled():
                channel = str(p.get("channel", "json")).upper()
                print(f"\n[{channel} JSON]\n{as_json_text(p.get('payload'))}")
            return
        if et == "error":
            print(f"\n[ERROR]\n{p.get('error', '')}")
            return
        if et == "clear_output":
            print("\n[SYS] Clear requested. Plain mode keeps terminal scrollback intact.")
            return
        if et == "quit":
            print("\n[SYS] Goodbye.")
            return
        if self._raw_json_enabled():
            print(f"\n[{et.upper()}]\n{as_json_text(p)}")


class AgentPlainCli:
    def __init__(self) -> None:
        self.core: Optional[AgentCore] = None
        self.sink = PlainConsoleEventSink(lambda: self.core)
        self.core = AgentCore(event_sink=self.sink.emit)

    def run(self) -> None:
        print(f"[SYS] {APP_NAME} plain mode online. Type /help. Type /quit to exit.")
        print("[SYS] Multiline paste support: start JSON with { or [, code with ```, or use /paste ... /endpaste.")

        while True:
            try:
                first_line = input("\nYou> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break

            raw_first = str(first_line or "")
            if not raw_first.strip():
                continue

            marker = raw_first.strip().lower()

            # /paste is only a multiline input collector.  After /endpaste,
            # submit the collected text exactly like normal terminal input; it
            # must not use a separate paste route or paste-specific policy.
            source_kind = "terminal"
            if marker == "/paste":
                text = collect_explicit_paste_plain_input()
                if not text.strip():
                    continue
            elif looks_like_code_fence_start(raw_first):
                text = collect_code_fence_plain_input(raw_first)
                if not text.strip():
                    continue
            elif looks_like_jsonish_multiline_start(raw_first) and not json_like_balance_complete(raw_first):
                text = collect_json_like_plain_input(raw_first)
                if not text.strip():
                    continue
            else:
                text = raw_first.strip()

            result = self.core.handle_input(text, source_kind=source_kind)
            if result.data.get("quit"):
                break
                                

# ============================================================
# WORKER
# ============================================================

class AgentWorker(threading.Thread):
    def __init__(self, core: AgentCore, text: str, bus: TuiEventBus) -> None:
        super().__init__(daemon=True)
        self.core = core
        self.text = text
        self.bus = bus

    def run(self) -> None:
        self.bus.emit("status", {"text": "running"})
        try:
            self.core.handle_input(self.text)
        finally:
            self.bus.emit("status", {"text": "idle"})


# ============================================================
# TUI HOST
# ============================================================

class AgentTuiApp:
    def __init__(self) -> None:
        global ttk
        ttk = require_ttk()
        self.bus = TuiEventBus()
        self.core = AgentCore(event_sink=self.bus.emit)
        self.worker: Optional[AgentWorker] = None
        self.busy = False
        self.output_buffer = ""
        self.state_buffer = ""
        self.current_assistant_open = False
        self.show_timestamps = DEFAULT_SHOW_TIMESTAMPS
        self.debug_enabled = False
        self.assistant_token_chars = 0
        self.assistant_stream_had_trailing_newline = False
        self.input_history: List[str] = []
        self.input_history_index: Optional[int] = None

        self.root = ttk.TTk()
        self.root.setLayout(ttk.TTkGridLayout())
        self.window = ttk.TTkWindow(parent=self.root, pos=(0, 0), size=(120, 42), title=APP_NAME, border=True)
        self.layout = ttk.TTkGridLayout()
        self.window.setLayout(self.layout)

        self.output_label = ttk.TTkLabel(text="Terminal Conversation", maxHeight=1)
        self.output = ttk.TTkTextEdit(readOnly=True)
        self.input = ttk.TTkLineEdit(hint="Type a command or natural-language request...")

        self.button_box = ttk.TTkContainer(layout=ttk.TTkHBoxLayout(), maxHeight=3)
        self.send_btn = ttk.TTkButton(parent=self.button_box, border=True, text="Send")
        self.prev_btn = ttk.TTkButton(parent=self.button_box, border=True, text="Prev")
        self.next_btn = ttk.TTkButton(parent=self.button_box, border=True, text="Next")
        self.clear_btn = ttk.TTkButton(parent=self.button_box, border=True, text="Clear")
        self.debug_btn = ttk.TTkButton(parent=self.button_box, border=True, text="Debug")
        self.save_btn = ttk.TTkButton(parent=self.button_box, border=True, text="Save")
        self.quit_btn = ttk.TTkButton(parent=self.button_box, border=True, text="Quit")

        self.layout.addWidget(self.output_label, 0, 0)
        self.layout.addWidget(self.output, 1, 0)
        self.layout.addWidget(self.input, 2, 0)
        self.layout.addWidget(self.button_box, 3, 0)

        self.send_btn.clicked.connect(self.submit_input)
        self.prev_btn.clicked.connect(lambda: self.recall_history(-1))
        self.next_btn.clicked.connect(lambda: self.recall_history(1))
        self.clear_btn.clicked.connect(self.clear_output)
        self.debug_btn.clicked.connect(self.toggle_debug)
        self.save_btn.clicked.connect(lambda: self.submit_text("/save"))
        self.quit_btn.clicked.connect(lambda: self.submit_text("/quit"))
        self.input.returnPressed.connect(self.submit_input)

        self.timer = ttk.TTkTimer()
        self.timer.timeout.connect(self.drain_events)
        self.timer.start(0.05)

        self.append_status("SYS", f"{APP_NAME} online. Type /help.")
        self.update_state_panel()

    def widget_set_text(self, widget: Any, text: str) -> None:
        try:
            widget.setText(text)
        except TypeError:
            widget.setText(text=text)
        try:
            widget.update()
        except Exception:
            pass

    def input_text(self) -> str:
        try:
            return str(self.input.text())
        except Exception:
            return ""

    def append_output(self, text: str) -> None:
        self.output_buffer += str(text)
        if len(self.output_buffer) > MAX_OUTPUT_CHARS:
            self.output_buffer = self.output_buffer[-MAX_OUTPUT_CHARS:]
        self.widget_set_text(self.output, self.output_buffer)
        self.scroll_output_to_bottom()

    def scroll_output_to_bottom(self) -> None:
        for method_name in ("moveCursorToEnd", "scrollToBottom"):
            method = getattr(self.output, method_name, None)
            if callable(method):
                try:
                    method()
                    return
                except Exception:
                    pass
        try:
            self.output.update()
        except Exception:
            pass

    def append_block(self, label: str, text: Any) -> None:
        self.append_output(terminal_block(label, text, timestamp=self.show_timestamps))

    def append_status(self, label: str, text: Any) -> None:
        self.append_output(compact_status_line(label, text, timestamp=self.show_timestamps))

    def clear_output(self) -> None:
        self.output_buffer = ""
        self.current_assistant_open = False
        self.assistant_token_chars = 0
        self.assistant_stream_had_trailing_newline = False
        self.widget_set_text(self.output, "")

    def update_state_panel(self) -> None:
        try:
            status = "busy" if self.busy else "idle"
            self.window.setTitle(f"{APP_NAME} [{status}]")
        except Exception:
            pass

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        try:
            self.send_btn.setText("Busy" if busy else "Send")
        except Exception:
            pass
        self.update_state_panel()

    def remember_input_history(self, text: str) -> None:
        text = str(text or "").strip()
        if not text:
            return
        if self.input_history and self.input_history[-1] == text:
            self.input_history_index = None
            return
        self.input_history.append(text)
        self.input_history = self.input_history[-MAX_INPUT_HISTORY:]
        self.input_history_index = None

    def recall_history(self, direction: int) -> None:
        if not self.input_history:
            return
        if self.input_history_index is None:
            self.input_history_index = len(self.input_history)
        self.input_history_index += direction
        self.input_history_index = max(0, min(len(self.input_history) - 1, self.input_history_index))
        self.widget_set_text(self.input, self.input_history[self.input_history_index])

    def toggle_debug(self) -> None:
        self.debug_enabled = not self.debug_enabled
        self.append_status("SYS", f"Debug {'enabled' if self.debug_enabled else 'disabled'}.")

    def handle_tui_command(self, text: str) -> bool:
        lowered = clean_text(text).lower()
        if lowered in {"/tui_clear", "/clear"}:
            self.clear_output()
            return True
        if lowered in {"/debug_on", "/tui_debug_on"}:
            self.debug_enabled = True
            self.append_status("SYS", "Debug enabled.")
            return True
        if lowered in {"/debug_off", "/tui_debug_off"}:
            self.debug_enabled = False
            self.append_status("SYS", "Debug disabled.")
            return True
        if lowered in {"/timestamps_on", "/time_on"}:
            self.show_timestamps = True
            self.append_status("SYS", "Timestamps enabled.")
            return True
        if lowered in {"/timestamps_off", "/time_off"}:
            self.show_timestamps = False
            self.append_status("SYS", "Timestamps disabled.")
            return True
        if lowered in {"/history", "/input_history"}:
            if not self.input_history:
                self.append_status("SYS", "Input history is empty.")
                return True
            lines = [f"{i}. {item}" for i, item in enumerate(self.input_history[-30:])]
            self.append_block("INPUT HISTORY", "\n".join(lines))
            return True
        return False

    def begin_assistant_stream(self) -> None:
        if self.current_assistant_open:
            return
        self.append_output(TERMINAL_BLOCK_SEPARATOR)
        self.append_output(f"{terminal_timestamp(self.show_timestamps)}[ASSISTANT]\n")
        self.current_assistant_open = True
        self.assistant_token_chars = 0
        self.assistant_stream_had_trailing_newline = False

    def append_assistant_token(self, token: str) -> None:
        token = str(token or "")
        if not token:
            return
        self.begin_assistant_stream()
        self.assistant_token_chars += len(token)
        self.assistant_stream_had_trailing_newline = token.endswith("\n")
        self.append_output(token)

    def end_assistant_stream(self) -> None:
        if not self.current_assistant_open:
            return
        if self.assistant_token_chars > 0 and not self.assistant_stream_had_trailing_newline:
            self.append_output("\n")
        self.current_assistant_open = False
        self.assistant_token_chars = 0
        self.assistant_stream_had_trailing_newline = False

    def submit_text(self, text: str) -> None:
        text = str(text or "").strip()
        if not text:
            return
        if self.handle_tui_command(text):
            return
        if self.busy:
            self.append_status("SYS", "Agent is busy. Wait for the current request to finish.")
            return
        self.remember_input_history(text)
        self.set_busy(True)
        self.current_assistant_open = False
        self.assistant_token_chars = 0
        self.assistant_stream_had_trailing_newline = False
        self.worker = AgentWorker(self.core, text, self.bus)
        self.worker.start()

    def submit_input(self) -> None:
        text = self.input_text().strip()
        if not text:
            return
        self.widget_set_text(self.input, "")
        self.submit_text(text)

    def drain_events(self) -> None:
        try:
            for event in self.bus.drain():
                self.handle_event(event)
            self.update_state_panel()
        finally:
            self.timer.start(0.05)

    def handle_event(self, event: AgentEvent) -> None:
        et = event.event_type
        p = event.payload
        if et == "user":
            self.append_output(TERMINAL_BLOCK_SEPARATOR)
            self.append_block("USER", p.get("text", ""))
            return
        if et == "status":
            self.set_busy(p.get("text") == "running")
            if not self.busy:
                self.current_assistant_open = False
            return
        if et == "route":
            if self.debug_enabled:
                d = p.get("decision", {})
                self.append_status("ROUTE", f"{d.get('command')} | confidence={d.get('confidence')}")
            return
        if et == "plan":
            if self.debug_enabled:
                plan = p.get("plan", {})
                self.append_status("PLAN", f"route={plan.get('route')} command={plan.get('command')}")
            return
        if et == "web":
            self.append_status("WEB", p.get("message", ""))
            return
        if et == "ground":
            self.append_status("GROUND", p.get("message", ""))
            return
        if et == "memory":
            self.append_status("MEMORY", p.get("message", ""))
            return
        if et == "text":
            channel = str(p.get("channel", "info")).upper()
            self.append_block(channel, p.get("text", ""))
            return
        if et == "json":
            if self.debug_enabled or self.core.registry.get("raw_tool_json_enabled", False):
                channel = str(p.get("channel", "json")).upper()
                self.append_block(f"{channel} JSON", as_json_text(p.get("payload")))
            return
        if et == "assistant_start":
            self.begin_assistant_stream()
            return
        if et == "stream_token":
            self.append_assistant_token(str(p.get("token", "")))
            return
        if et == "assistant_done":
            self.end_assistant_stream()
            return
        if et == "error":
            self.append_block("ERROR", p.get("error", ""))
            return
        if et == "clear_output":
            self.clear_output()
            return
        if et == "quit":
            self.append_status("SYS", "Goodbye.")
            self.request_quit()
            return
        if et == "done":
            self.set_busy(False)
            self.current_assistant_open = False
            self.assistant_token_chars = 0
            self.assistant_stream_had_trailing_newline = False
            return
        if self.debug_enabled:
            self.append_block(et.upper(), as_json_text(p))

    def request_quit(self) -> None:
        try:
            self.root.quit()
        except Exception:
            try:
                ttk.TTkHelper.quit()
            except Exception:
                raise SystemExit(0)

    def run(self) -> None:
        self.root.mainloop()


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    if "--tui" in sys.argv:
        app = AgentTuiApp()
        app.run()
        return 0

    app = AgentPlainCli()
    app.run()
    return 0
    

if __name__ == "__main__":
    raise SystemExit(main())
