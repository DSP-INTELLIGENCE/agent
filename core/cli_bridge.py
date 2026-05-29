from __future__ import annotations

import ast
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.helpers import clean_text, truncate_text

CLI_MANIFEST_SCHEMA_VERSION = "agent-cli-plugin-v1"
DEFAULT_CLI_TIMEOUT_SECONDS = 30
DEFAULT_MAX_STDOUT_CHARS = 60_000
DEFAULT_MAX_STDERR_CHARS = 20_000
MAX_SCAN_FILES = 500

VALID_LONG_SWITCH_RE = re.compile(r"^--[A-Za-z0-9][A-Za-z0-9_-]*$")
VALID_SHORT_SWITCH_RE = re.compile(r"^-[A-Za-z]$")
# Fallback scanner: valid long switches or single-letter short switches only.
# This intentionally does not match junk strings such as -0123456789tfn or -GGUF.
DASH_FLAG_RE = re.compile(r"(?<![A-Za-z0-9_])(--[A-Za-z0-9][A-Za-z0-9_-]*|-[A-Za-z])(?![A-Za-z0-9_-])")

SHELL_META_TOKENS = {";", "&&", "||", "|", ">", ">>", "<", "`"}


def _is_valid_switch(flag: str) -> bool:
    value = clean_text(flag)
    return bool(VALID_LONG_SWITCH_RE.match(value) or VALID_SHORT_SWITCH_RE.match(value))


def _clean_switch(flag: Any) -> str:
    value = clean_text(str(flag or ""))
    # Preserve --flag=value in user arguments, but manifest declarations should
    # store just the switch name.
    if "=" in value:
        value = value.split("=", 1)[0]
    return value


def _safe_id(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_.-]+", ".", clean_text(text))
    value = re.sub(r"[.]{2,}", ".", value).strip("._-").lower()
    return value or "tool"


def _project_relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        try:
            return os.path.relpath(path.resolve(), root.resolve())
        except Exception:
            return str(path)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _looks_like_python_script(path: Path) -> bool:
    return path.suffix.lower() == ".py"


def _extract_doc_description(text: str) -> str:
    try:
        mod = ast.parse(text)
        doc = ast.get_docstring(mod) or ""
    except Exception:
        doc = ""
    lines = [line.strip() for line in doc.splitlines() if line.strip()]
    if not lines:
        return "CLI tool."
    # Skip shebang-ish titles and keep a compact first useful sentence.
    return truncate_text(lines[0], 220)


def _extract_mega_manifest(text: str) -> Dict[str, Any]:
    """Best-effort static extraction of MEGA_TOOL_MANIFEST without executing a tool."""
    try:
        mod = ast.parse(text)
    except Exception:
        return {}
    for node in mod.body:
        value_node = None
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "MEGA_TOOL_MANIFEST":
                    value_node = node.value
                    break
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == "MEGA_TOOL_MANIFEST":
                value_node = node.value
        if value_node is not None:
            try:
                value = ast.literal_eval(value_node)
                return value if isinstance(value, dict) else {}
            except Exception:
                return {}
    return {}


def _extract_argparse_flags(text: str) -> List[str]:
    """Extract literal argparse add_argument switches with AST when possible.

    This avoids treating arbitrary dash-prefixed strings in prompts, examples,
    regexes, or model names as CLI switches.
    """
    flags = set()
    try:
        mod = ast.parse(text or "")
    except Exception:
        return []
    for node in ast.walk(mod):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_argument"):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                flag = _clean_switch(arg.value)
                if flag.startswith("-") and _is_valid_switch(flag):
                    flags.add(flag)
            elif isinstance(arg, (ast.Tuple, ast.List)):
                for elt in arg.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        flag = _clean_switch(elt.value)
                        if flag.startswith("-") and _is_valid_switch(flag):
                            flags.add(flag)
    return sorted(flags)


def _extract_cli_flags(text: str, manifest: Optional[Dict[str, Any]] = None) -> List[str]:
    flags = set()

    # 1. Explicit manifest declarations are highest confidence.
    if isinstance(manifest, dict):
        raw = manifest.get("cli_flags")
        if isinstance(raw, list):
            for item in raw:
                flag = _clean_switch(item)
                if flag.startswith("-") and _is_valid_switch(flag):
                    flags.add(flag)
        inputs = manifest.get("inputs")
        if isinstance(inputs, dict):
            for spec in inputs.values():
                if isinstance(spec, dict):
                    flag = _clean_switch(spec.get("cli"))
                    if flag.startswith("-") and _is_valid_switch(flag):
                        flags.add(flag)

    # 2. argparse add_argument literal switches are next-best.
    flags.update(_extract_argparse_flags(text))

    # 3. Narrow fallback: only valid long switches and single-letter short switches.
    # This is intentionally conservative to avoid source-string noise.
    for raw_flag in DASH_FLAG_RE.findall(text or ""):
        flag = _clean_switch(raw_flag)
        if _is_valid_switch(flag):
            flags.add(flag)

    flags.add("--help")
    flags.add("-h")
    return sorted(flags)


def _extract_allowed_positionals(manifest: Optional[Dict[str, Any]] = None, text: str = "") -> List[str]:
    out = set()
    if isinstance(manifest, dict):
        raw_commands = manifest.get("commands")
        if isinstance(raw_commands, list):
            for item in raw_commands:
                if isinstance(item, dict):
                    name = clean_text(item.get("name") or "")
                    if name:
                        out.add(name)
                elif isinstance(item, str) and clean_text(item):
                    out.add(clean_text(item))
        primary = clean_text(manifest.get("primary_command") or "")
        if primary:
            out.add(primary)
    # Best-effort argparse choices=["generate", "manifest"] fallback.
    for m in re.finditer(r"choices\s*=\s*\[([^\]]+)\]", text or "", flags=re.S):
        body = m.group(1)
        for q in re.finditer(r'[\'\"]([A-Za-z0-9_.-]+)[\'\"]', body):
            out.add(q.group(1))
    return sorted(out)


def _format_completed_process(argv: List[str], proc: subprocess.CompletedProcess[str], *, max_stdout: int, max_stderr: int) -> str:
    stdout = truncate_text(proc.stdout or "", max_stdout)
    stderr = truncate_text(proc.stderr or "", max_stderr)
    lines = ["$ " + " ".join(shlex.quote(x) for x in argv), f"exit_code: {proc.returncode}"]
    if stdout:
        lines += ["", "stdout:", stdout.rstrip()]
    if stderr:
        lines += ["", "stderr:", stderr.rstrip()]
    return "\n".join(lines)


@dataclass
class CLIToolRecord:
    tool_id: str
    name: str
    description: str
    command: List[str]
    cwd: str = "."
    timeout_seconds: int = DEFAULT_CLI_TIMEOUT_SECONDS
    input_mode: str = "none"  # none | stdin
    output_mode: str = "stdout"
    allowed_args: List[str] = field(default_factory=list)
    value_args: List[str] = field(default_factory=list)
    boolean_args: List[str] = field(default_factory=list)
    allowed_positionals: List[str] = field(default_factory=list)
    default_args: List[str] = field(default_factory=list)
    allow_free_args: bool = False
    max_stdout_chars: int = DEFAULT_MAX_STDOUT_CHARS
    max_stderr_chars: int = DEFAULT_MAX_STDERR_CHARS
    manifest_path: str = ""
    manifest: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "description": self.description,
            "command": self.command,
            "cwd": self.cwd,
            "timeout_seconds": self.timeout_seconds,
            "input_mode": self.input_mode,
            "output_mode": self.output_mode,
            "allowed_args": self.allowed_args,
            "value_args": self.value_args,
            "boolean_args": self.boolean_args,
            "allowed_positionals": self.allowed_positionals,
            "default_args": self.default_args,
            "allow_free_args": self.allow_free_args,
            "max_stdout_chars": self.max_stdout_chars,
            "max_stderr_chars": self.max_stderr_chars,
            "manifest_path": self.manifest_path,
        }


class CLIPluginBridge:
    """Generic manifest-driven bridge from agent commands to local CLI tools.

    This intentionally uses subprocess with shell=False. A JSON manifest declares
    the command vector, allowed switches, allowed positional subcommands, cwd,
    timeouts, and output caps. It is generic and not tied to any specific tool set.
    """

    def __init__(self, root: Path, manifest_dir: Path) -> None:
        self.root = root.resolve()
        self.manifest_dir = manifest_dir
        # The agent repo owns the bridge, but tool code may live in the sibling
        # standalone mega-tools repo. Keep the allowlist narrow: project root
        # plus ../mega-tools only. This preserves shell=False and manifest arg
        # validation while no longer assuming tools are embedded in agent/.
        self.external_tool_roots = self.discover_external_tool_roots()
        self.records: Dict[str, CLIToolRecord] = {}
        self.errors: List[Dict[str, str]] = []

    def discover_external_tool_roots(self) -> List[Path]:
        roots: List[Path] = []
        sibling_mega_tools = (self.root.parent / "mega-tools").resolve()
        roots.append(sibling_mega_tools)
        return roots

    def is_allowed_tool_path(self, path: Path) -> bool:
        if _is_within(path, self.root):
            return True
        return any(_is_within(path, root) for root in self.external_tool_roots)

    def load(self) -> Dict[str, Any]:
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        self.records.clear()
        self.errors.clear()
        for path in sorted(self.manifest_dir.glob("*.json")):
            try:
                record = self.load_manifest(path)
                if record.tool_id in self.records:
                    raise RuntimeError(f"duplicate cli tool id: {record.tool_id}")
                self.records[record.tool_id] = record
            except Exception as exc:
                self.errors.append({"path": str(path), "error": str(exc)})
        return {"loaded_count": len(self.records), "error_count": len(self.errors), "errors": list(self.errors)}

    def load_manifest(self, path: Path) -> CLIToolRecord:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError("manifest must be a JSON object")
        if data.get("schema_version") != CLI_MANIFEST_SCHEMA_VERSION:
            raise RuntimeError(f"unsupported schema_version: {data.get('schema_version')}")
        tool_id = _safe_id(data.get("tool_id") or path.stem)
        command = data.get("command")
        if not isinstance(command, list) or not all(isinstance(x, str) and x.strip() for x in command):
            raise RuntimeError("command must be a non-empty list of strings")
        cwd = clean_text(data.get("cwd") or ".") or "."
        cwd_path = self.resolve_cwd(cwd)
        self.validate_command_paths(command, cwd_path)
        allowed_args = [x for x in data.get("allowed_args", []) if isinstance(x, str) and _is_valid_switch(x)]
        value_args = [x for x in data.get("value_args", []) if isinstance(x, str) and _is_valid_switch(x)]
        boolean_args = [x for x in data.get("boolean_args", []) if isinstance(x, str) and _is_valid_switch(x)]
        allowed_positionals = [clean_text(x) for x in data.get("allowed_positionals", []) if clean_text(x)]
        default_args = [str(x) for x in data.get("default_args", []) if str(x).strip()]
        return CLIToolRecord(
            tool_id=tool_id,
            name=clean_text(data.get("name") or tool_id),
            description=clean_text(data.get("description") or "CLI tool."),
            command=command,
            cwd=cwd,
            timeout_seconds=max(1, min(int(data.get("timeout_seconds", DEFAULT_CLI_TIMEOUT_SECONDS)), 600)),
            input_mode=clean_text(data.get("input_mode") or "none").lower() or "none",
            output_mode=clean_text(data.get("output_mode") or "stdout").lower() or "stdout",
            allowed_args=allowed_args,
            value_args=value_args,
            boolean_args=boolean_args,
            allowed_positionals=allowed_positionals,
            default_args=default_args,
            allow_free_args=bool(data.get("allow_free_args", False)),
            max_stdout_chars=max(1000, min(int(data.get("max_stdout_chars", DEFAULT_MAX_STDOUT_CHARS)), 500_000)),
            max_stderr_chars=max(1000, min(int(data.get("max_stderr_chars", DEFAULT_MAX_STDERR_CHARS)), 200_000)),
            manifest_path=str(path),
            manifest=data,
        )

    def resolve_cwd(self, cwd: str) -> Path:
        path = Path(cwd)
        if not path.is_absolute():
            path = self.root / path
        path = path.resolve()
        if not _is_within(path, self.root):
            raise RuntimeError(f"cwd escapes project root: {cwd}")
        return path

    def validate_command_paths(self, command: List[str], cwd_path: Path) -> None:
        # Interpreter/binary name may be from PATH. Script path arguments must stay project-local.
        for token in command[1:]:
            if token.endswith(".py") or "/" in token or "\\" in token:
                candidate = Path(token)
                if not candidate.is_absolute():
                    candidate = self.root / token
                candidate = candidate.resolve()
                if not self.is_allowed_tool_path(candidate):
                    allowed = ", ".join(str(root) for root in [self.root, *self.external_tool_roots])
                    raise RuntimeError(f"command path escapes allowed tool roots: {token} (allowed: {allowed})")

    def is_allowed_path_positional(self, record: CLIToolRecord, token: str) -> bool:
        """Return true when a positional path matches a manifest allowlist policy.

        This is intentionally narrow: it only applies to positional arguments,
        keeps allow_free_args false, blocks traversal/absolute paths before this
        method is called, and resolves accepted paths inside a fixed project-local
        directory.
        """
        value = clean_text(token).replace("\\", "/")
        if not value or value.startswith("/") or ".." in value.split("/"):
            return False
        policies = record.manifest.get("allowed_path_positionals", [])
        if not isinstance(policies, list):
            return False
        for policy in policies:
            if isinstance(policy, str):
                prefix = clean_text(policy).replace("\\", "/")
                suffix = ""
            elif isinstance(policy, dict):
                prefix = clean_text(policy.get("prefix") or "").replace("\\", "/")
                suffix = clean_text(policy.get("suffix") or "").replace("\\", "/")
            else:
                continue
            if not prefix:
                continue
            if not prefix.endswith("/"):
                prefix += "/"
            if not value.startswith(prefix):
                continue
            if suffix and not value.endswith(suffix):
                continue
            candidate = (self.root / value).resolve()
            base = (self.root / prefix).resolve()
            if _is_within(candidate, base):
                return True
        return False

    def list_tools(self) -> List[Dict[str, Any]]:
        return [rec.to_dict() for _, rec in sorted(self.records.items())]

    def get_tool(self, tool_id: str) -> Optional[CLIToolRecord]:
        key = _safe_id(tool_id)
        return self.records.get(key)

    def validate_user_args(self, record: CLIToolRecord, arg_text: str) -> List[str]:
        try:
            tokens = shlex.split(arg_text or "")
        except ValueError as exc:
            raise RuntimeError(f"could not parse tool args: {exc}") from exc
        if not tokens:
            return []
        allowed_args = set(record.allowed_args)
        value_args = set(record.value_args)
        boolean_args = set(record.boolean_args)
        allowed_positionals = set(record.allowed_positionals)
        validated: List[str] = []
        expecting_value_for: Optional[str] = None
        for token in tokens:
            if token in SHELL_META_TOKENS or any(meta in token for meta in (";", "&&", "||", "`", "$(", ">", "<")):
                raise RuntimeError(f"blocked shell metacharacter in argument: {token}")
            if token.startswith("/") or ".." in token.replace("\\", "/").split("/"):
                raise RuntimeError(f"blocked unsafe path-like argument: {token}")

            if expecting_value_for:
                validated.append(token)
                expecting_value_for = None
                continue

            if token.startswith("-"):
                flag = token.split("=", 1)[0]
                if flag not in allowed_args:
                    raise RuntimeError(f"switch not allowed for {record.tool_id}: {flag}")
                validated.append(token)
                if "=" not in token:
                    if flag in boolean_args:
                        expecting_value_for = None
                    elif value_args:
                        if flag in value_args:
                            expecting_value_for = flag
                    else:
                        # Backwards-compatible behavior for old manifests: if the
                        # next token is not a flag, allow it as this flag's value.
                        expecting_value_for = flag
                continue

            if token in allowed_positionals or self.is_allowed_path_positional(record, token) or record.allow_free_args:
                validated.append(token)
                continue
            raise RuntimeError(f"positional argument not allowed for {record.tool_id}: {token}")
        return validated

    def run_tool(self, tool_id: str, arg_text: str = "", stdin_text: str = "") -> Dict[str, Any]:
        record = self.get_tool(tool_id)
        if not record:
            return {"ok": False, "handled": True, "message": f"No CLI tool registered: {tool_id}", "errors": ["tool_not_found"], "data": {}}
        try:
            user_args = self.validate_user_args(record, arg_text)
        except RuntimeError as exc:
            return {
                "ok": False,
                "handled": True,
                "message": str(exc),
                "errors": ["argument_validation_failed"],
                "data": {"tool_id": record.tool_id, "args_text": arg_text},
            }
        argv = list(record.command) + list(record.default_args) + user_args
        cwd = self.resolve_cwd(record.cwd)
        stdin_payload: Optional[str] = None
        if record.input_mode == "stdin" and stdin_text:
            stdin_payload = stdin_text
        try:
            proc = subprocess.run(
                argv,
                cwd=str(cwd),
                text=True,
                input=stdin_payload,
                capture_output=True,
                timeout=record.timeout_seconds,
                check=False,
                shell=False,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "handled": True,
                "message": f"CLI tool timed out after {record.timeout_seconds} seconds: {record.tool_id}",
                "errors": ["timeout"],
                "data": {"tool_id": record.tool_id, "argv": argv},
            }
        display = _format_completed_process(argv, proc, max_stdout=record.max_stdout_chars, max_stderr=record.max_stderr_chars)
        return {
            "ok": proc.returncode == 0,
            "handled": True,
            "message": f"CLI tool exited with code {proc.returncode}: {record.tool_id}",
            "display": {"type": "text", "text": display},
            "data": {"tool_id": record.tool_id, "argv": argv, "cwd": str(cwd), "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr},
            "errors": [] if proc.returncode == 0 else [f"exit_code_{proc.returncode}"],
        }

    def help_tool(self, tool_id: str) -> Dict[str, Any]:
        record = self.get_tool(tool_id)
        if not record:
            return {"ok": False, "handled": True, "message": f"No CLI tool registered: {tool_id}", "errors": ["tool_not_found"], "data": {}}
        argv = list(record.command) + ["--help"]
        cwd = self.resolve_cwd(record.cwd)
        try:
            proc = subprocess.run(argv, cwd=str(cwd), text=True, capture_output=True, timeout=min(record.timeout_seconds, 20), check=False, shell=False)
        except subprocess.TimeoutExpired:
            return {"ok": False, "handled": True, "message": f"Help timed out: {tool_id}", "errors": ["timeout"], "data": {}}
        display = _format_completed_process(argv, proc, max_stdout=record.max_stdout_chars, max_stderr=record.max_stderr_chars)
        return {"ok": proc.returncode == 0, "handled": True, "message": f"Help for {tool_id}", "display": {"type": "text", "text": display}, "data": {"tool_id": tool_id, "stdout": proc.stdout, "stderr": proc.stderr, "returncode": proc.returncode}}

    def draft_manifest_for_script(self, script_path: Path) -> Dict[str, Any]:
        text = script_path.read_text(encoding="utf-8", errors="replace")[:2_000_000]
        rel = _project_relative(script_path, self.root)
        mega_manifest = _extract_mega_manifest(text)
        tool_id = _safe_id(mega_manifest.get("tool_id") or script_path.stem)
        description = clean_text(mega_manifest.get("description") or _extract_doc_description(text))
        name = clean_text(mega_manifest.get("name") or script_path.stem)
        allowed_args = _extract_cli_flags(text, mega_manifest)
        allowed_positionals = _extract_allowed_positionals(mega_manifest, text)
        input_mode = "stdin" if "--stdin" in allowed_args else "none"
        return {
            "schema_version": CLI_MANIFEST_SCHEMA_VERSION,
            "tool_id": tool_id,
            "name": name,
            "description": description,
            "command": ["python3", rel],
            "cwd": ".",
            "timeout_seconds": DEFAULT_CLI_TIMEOUT_SECONDS,
            "input_mode": input_mode,
            "output_mode": "stdout",
            "allowed_args": allowed_args,
            "allowed_positionals": allowed_positionals,
            "default_args": [],
            "allow_free_args": False,
            "max_stdout_chars": DEFAULT_MAX_STDOUT_CHARS,
            "max_stderr_chars": DEFAULT_MAX_STDERR_CHARS,
            "source": {"path": rel, "scanner": "agent.cli_bridge"},
        }

    def scan_path(self, path_text: str, *, write: bool = True) -> Dict[str, Any]:
        raw = clean_text(path_text or "") or "."
        path = Path(raw)
        if not path.is_absolute():
            path = self.root / path
        path = path.resolve()
        if not self.is_allowed_tool_path(path):
            allowed = ", ".join(str(root) for root in [self.root, *self.external_tool_roots])
            raise RuntimeError(f"scan path escapes allowed tool roots: {raw} (allowed: {allowed})")
        if not path.exists():
            raise RuntimeError(f"scan path does not exist: {raw}")
        files: List[Path]
        if path.is_file():
            files = [path]
        else:
            files = sorted([p for p in path.rglob("*") if p.is_file() and (_looks_like_python_script(p) or os.access(p, os.X_OK))])[:MAX_SCAN_FILES]
        created: List[Dict[str, Any]] = []
        skipped: List[Dict[str, str]] = []
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        for item in files:
            try:
                if _looks_like_python_script(item):
                    manifest = self.draft_manifest_for_script(item)
                else:
                    rel = _project_relative(item, self.root)
                    tool_id = _safe_id(item.stem)
                    manifest = {
                        "schema_version": CLI_MANIFEST_SCHEMA_VERSION,
                        "tool_id": tool_id,
                        "name": item.name,
                        "description": "Executable CLI tool.",
                        "command": [rel],
                        "cwd": ".",
                        "timeout_seconds": DEFAULT_CLI_TIMEOUT_SECONDS,
                        "input_mode": "none",
                        "output_mode": "stdout",
                        "allowed_args": ["--help", "-h"],
                        "allowed_positionals": [],
                        "default_args": [],
                        "allow_free_args": False,
                        "max_stdout_chars": DEFAULT_MAX_STDOUT_CHARS,
                        "max_stderr_chars": DEFAULT_MAX_STDERR_CHARS,
                        "source": {"path": rel, "scanner": "agent.cli_bridge"},
                    }
                out_path = self.manifest_dir / f"{manifest['tool_id']}.json"
                if write:
                    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                created.append({"tool_id": manifest["tool_id"], "name": manifest.get("name", ""), "path": str(out_path), "source": manifest.get("source", {})})
            except Exception as exc:
                skipped.append({"path": str(item), "error": str(exc)})
        if write:
            self.load()
        return {"ok": True, "scanned_path": str(path), "created_count": len(created), "skipped_count": len(skipped), "created": created, "skipped": skipped, "loaded_count": len(self.records)}
