from __future__ import annotations

from typing import List

from core.constants import MAX_MULTILINE_INPUT_CHARS, MAX_MULTILINE_INPUT_LINES

# PLAIN CLI MULTILINE INPUT HELPERS
# ============================================================

def looks_like_jsonish_multiline_start(text: str) -> bool:
    stripped = str(text or "").lstrip()
    return stripped.startswith("{") or stripped.startswith("[")


def looks_like_code_fence_start(text: str) -> bool:
    stripped = str(text or "").lstrip()
    return stripped.startswith("```")


def json_like_balance_complete(text: str) -> bool:
    """
    Return True when a JSON/Python-dict-like pasted block appears balanced.

    This intentionally does not require json.loads() success because users often paste
    fragments such as:
        {
          ...
        },
    where the trailing comma is valid inside a larger list but invalid as standalone JSON.
    """
    raw = str(text or "")
    if not raw.strip():
        return True

    stack: List[str] = []
    in_string = False
    quote_char = ""
    escape = False

    for ch in raw:
        if escape:
            escape = False
            continue

        if in_string:
            if ch == "\\":
                escape = True
            elif ch == quote_char:
                in_string = False
                quote_char = ""
            continue

        if ch in {'"', "'"}:
            in_string = True
            quote_char = ch
            continue

        if ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in {"}", "]"}:
            if stack and stack[-1] == ch:
                stack.pop()
            elif stack:
                # Mismatched closer: pop one level so a pasted malformed block
                # does not trap the terminal forever.
                stack.pop()
            else:
                # Extra closer after completion, e.g. pasted fragment residue.
                continue

    return not stack and not in_string


def collect_json_like_plain_input(first_line: str) -> str:
    lines = [str(first_line or "")]
    total_chars = sum(len(x) for x in lines)

    print("[PASTE] JSON-like multiline input detected. Continue paste; use /endpaste to submit or /cancelpaste to cancel.")

    while not json_like_balance_complete("\n".join(lines)):
        if len(lines) >= MAX_MULTILINE_INPUT_LINES or total_chars >= MAX_MULTILINE_INPUT_CHARS:
            print("[PASTE] Multiline input limit reached; submitting what was collected.")
            break

        try:
            line = input("... ")
        except EOFError:
            break

        marker = line.strip().lower()
        if marker == "/cancelpaste":
            print("[PASTE] Cancelled.")
            return ""
        if marker == "/endpaste":
            break

        lines.append(line)
        total_chars += len(line)

    return "\n".join(lines)


def collect_code_fence_plain_input(first_line: str) -> str:
    lines = [str(first_line or "")]
    total_chars = sum(len(x) for x in lines)

    print("[PASTE] Code fence detected. Continue paste; closing ``` submits. Use /cancelpaste to cancel.")

    while True:
        if len(lines) >= MAX_MULTILINE_INPUT_LINES or total_chars >= MAX_MULTILINE_INPUT_CHARS:
            print("[PASTE] Multiline input limit reached; submitting what was collected.")
            break

        try:
            line = input("... ")
        except EOFError:
            break

        marker = line.strip().lower()
        if marker == "/cancelpaste":
            print("[PASTE] Cancelled.")
            return ""

        lines.append(line)
        total_chars += len(line)

        if len(lines) > 1 and line.strip().startswith("```"):
            break

    return "\n".join(lines)


def collect_explicit_paste_plain_input() -> str:
    lines: List[str] = []
    total_chars = 0

    print("[PASTE] Paste multiline text now.")
    print("[PASTE] End with /endpaste. Cancel with /cancelpaste.")

    while True:
        if len(lines) >= MAX_MULTILINE_INPUT_LINES or total_chars >= MAX_MULTILINE_INPUT_CHARS:
            print("[PASTE] Multiline input limit reached; submitting what was collected.")
            break

        try:
            line = input("... ")
        except EOFError:
            break

        marker = line.strip().lower()
        if marker == "/cancelpaste":
            print("[PASTE] Cancelled.")
            return ""
        if marker == "/endpaste":
            break

        lines.append(line)
        total_chars += len(line)

    return "\n".join(lines)
