from __future__ import annotations

from pathlib import Path

# CONSTANTS
# ============================================================

APP_NAME = "Agent"
DEFAULT_OLLAMA_BASE = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "hf.co/DevsDoCode/LLama-3-8b-Uncensored-Q4_K_M-GGUF:latest"

DATA_DIR = Path("data_agent")
SESSIONS_DIR = DATA_DIR / "sessions"
PLUGINS_DIR = DATA_DIR / "plugins"
PLUGIN_DATA_DIR = DATA_DIR / "plugin_data"
DEFAULT_SESSION_NAME = "session.json"
CONFIG_DIR = DATA_DIR / "config"
AGENT_CONFIG_PATH = CONFIG_DIR / "agent_config.json"
PROMPTS_CONFIG_PATH = CONFIG_DIR / "prompts.json"
METADATA_CONFIG_PATH = CONFIG_DIR / "metadata.json"
PERSONALITIES_CONFIG_PATH = CONFIG_DIR / "personalities.json"


MAX_WEB_TEXT_CHARS = 30000
MAX_WEB_HTML_CHARS = 2_000_000
MAX_LINKS_PER_PAGE = 100
MAX_SEARCH_RESULTS = 10
MAX_MEMORY_RESULTS = 8
MAX_CHAT_CONTEXT_MESSAGES = 8
MAX_OUTPUT_CHARS = 120_000
DEFAULT_SHOW_TIMESTAMPS = False
MAX_INPUT_HISTORY = 200
MAX_MULTILINE_INPUT_LINES = 5000
MAX_MULTILINE_INPUT_CHARS = 500_000
TERMINAL_BLOCK_SEPARATOR = "\n"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 Agent/1.0 "
    "(local terminal research assistant)"
)

WIKIPEDIA_API_BASE = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_REST_BASE = "https://en.wikipedia.org/api/rest_v1/page/summary"
GROUNDING_MODE = "wikipedia_first"
GROUNDING_NO_SOURCE_MESSAGE = (
    "I don’t know from the available sources. I could not find reliable grounding for that."
)
GROUNDING_WEAK_SOURCE_MESSAGE = (
    "I found possible search results, but I could not fetch enough source text to verify the answer."
)

TRUSTED_SOURCE_PRIORITY = [
    "wikipedia.org",
    "imdb.com",
    "docs.python.org",
    "developer.mozilla.org",
    "github.com",
    "stackoverflow.com",
    "themoviedb.org",
    "letterboxd.com",
]

GROUNDING_MAX_SEARCH_RESULTS_PER_SOURCE = 4
GROUNDING_MAX_FETCHED_SOURCES = 3

GROUNDING_SOURCE_PROFILES = {
    "film": [
        "imdb.com",
        "themoviedb.org",
        "letterboxd.com",
        "mubi.com",
        "rottentomatoes.com",
    ],
    "software": [
        "docs.python.org",
        "developer.mozilla.org",
        "github.com",
        "readthedocs.io",
        "pypi.org",
    ],
    "general_reference": [
        "wikipedia.org",
        "britannica.com",
    ],
}

FACTUAL_LOOKUP_PREFIXES = (
    "what is ", "what are ", "who is ", "who was ", "when was ", "when did ",
    "where is ", "where was ", "which ", "why did ", "how old ", "is there ",
    "does ", "did ", "was ", "were ",
)

ALLOWED_FETCH_CONTENT_TYPES = [
    "text/html",
    "text/plain",
    "application/json",
    "application/xhtml+xml",
    "application/xml",
    "text/xml",
]



# PLUGIN CONTRACT CONSTANTS
# ============================================================

PLUGIN_SCHEMA_VERSION = "agent-plugin-v1"

PLUGIN_ALLOWED_SAFETY_LEVELS = {
    "read_only",
    "local_only",
    "file_write",
    "network",
    "external_process",
    "high_risk",
}

PLUGIN_PROTECTED_COMMAND_PREFIXES = (
    "system.",
    "chat.",
    "memory.",
    "web.",
    "agent.",
)

PLUGIN_MAX_FILES = 100
# ============================================================
