from __future__ import annotations

import importlib.util
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


def test_codec_prompt_routes_to_prompt_lane(monkeypatch) -> None:
    codec = _load_codec()
    calls = []

    def fake_run_text_lane(lane: str, text: list[str], *, label: str) -> int:
        calls.append((lane, text, label))
        return 0

    monkeypatch.setattr(codec, "_run_text_lane", fake_run_text_lane)

    assert codec.main(["prompt", "hello", "world"]) == 0
    assert calls == [("/prompt", ["hello", "world"], "prompt")]


def test_codec_ground_routes_to_ground_lane(monkeypatch) -> None:
    codec = _load_codec()
    calls = []

    def fake_run_text_lane(lane: str, text: list[str], *, label: str) -> int:
        calls.append((lane, text, label))
        return 0

    monkeypatch.setattr(codec, "_run_text_lane", fake_run_text_lane)

    assert codec.main(["ground", "what", "is", "pie?"]) == 0
    assert calls == [("/ground", ["what", "is", "pie?"], "ground")]


def test_codec_ground_help_mentions_ground_lane(capsys) -> None:
    codec = _load_codec()
    parser = codec.build_parser()

    try:
        parser.parse_args(["ground", "--help"])
    except SystemExit as exc:
        assert exc.code == 0

    out = capsys.readouterr().out
    assert "/ground" in out
    assert "/question" not in out
