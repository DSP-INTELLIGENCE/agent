from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path


def _install_batch_runner_stub() -> None:
    fake_batch_runner = types.ModuleType("core.batch_runner")

    def fake_run_command(command: str):
        return types.SimpleNamespace(ok=True, returncode=0, stdout="", stderr="", mode="stub", input=command)

    def fake_format_result(result) -> str:
        return getattr(result, "stdout", "") or ""

    fake_batch_runner.run_command = fake_run_command
    fake_batch_runner.format_result = fake_format_result
    sys.modules["core.batch_runner"] = fake_batch_runner


def _load_codec():
    _install_batch_runner_stub()
    sys.modules.pop("codec_test_module", None)
    path = Path("codec.py")
    spec = importlib.util.spec_from_file_location("codec_test_module", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules["codec_test_module"] = module
    spec.loader.exec_module(module)
    return module


def test_codec_status_text_mentions_lanes_and_patch_workflow(monkeypatch, capsys) -> None:
    codec = _load_codec()

    def fake_git_output(*args: str) -> str:
        mapping = {
            ("status", "--short", "--untracked-files=all"): "",
            ("branch", "--show-current"): "main",
            ("rev-parse", "--short", "HEAD"): "abc1234",
        }
        return mapping.get(tuple(args), "")

    monkeypatch.setattr(codec, "_git_output", fake_git_output)

    assert codec.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "codec frontend: available" in out
    assert "prompt -> /prompt" in out
    assert "ground -> /ground" in out
    assert "patch operator: codec-patch.py" in out
    assert "patch workflow: review -> publish -> merge-cleanup" in out
    assert "branch: main" in out
    assert "head: abc1234" in out
    assert "clean: true" in out


def test_codec_status_json_has_expected_contract(monkeypatch, capsys) -> None:
    codec = _load_codec()

    def fake_git_output(*args: str) -> str:
        mapping = {
            ("status", "--short", "--untracked-files=all"): " M codec.py",
            ("branch", "--show-current"): "patch/test",
            ("rev-parse", "--short", "HEAD"): "def5678",
        }
        return mapping.get(tuple(args), "")

    monkeypatch.setattr(codec, "_git_output", fake_git_output)

    assert codec.main(["status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["codec_frontend"] == "available"
    assert payload["answer_lanes"]["prompt"] == "/prompt"
    assert payload["answer_lanes"]["ground"] == "/ground"
    assert payload["patch_operator"] == "codec-patch.py"
    assert payload["patch_workflow"] == ["review", "publish", "merge-cleanup"]
    assert payload["repo"]["branch"] == "patch/test"
    assert payload["repo"]["head"] == "def5678"
    assert payload["repo"]["clean"] is False
    assert payload["repo"]["status_short"] == " M codec.py"


def test_codec_status_help_mentions_json_flag(capsys) -> None:
    codec = _load_codec()
    parser = codec.build_parser()

    try:
        parser.parse_args(["status", "--help"])
    except SystemExit as exc:
        assert exc.code == 0

    out = capsys.readouterr().out
    assert "Show codec status and diagnostics" in out
    assert "--json" in out
