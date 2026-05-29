from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_patch_install():
    path = ROOT / "core" / "patch_install.py"
    spec = importlib.util.spec_from_file_location("patch_install_test_module", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, text=True, capture_output=True)


def test_changed_files_manifest_report_includes_untracked_files(tmp_path, capsys) -> None:
    patch_install = _load_patch_install()
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")

    tracked = repo / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    tracked.write_text("after\n", encoding="utf-8")

    untracked = repo / "new.txt"
    untracked.write_text("new\n", encoding="utf-8")

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "changed-files.txt").write_text("tracked.txt\nnew.txt\n", encoding="utf-8")

    patch_install.print_changed_files_manifest_report(repo, pkg)

    out = capsys.readouterr().out
    assert "== report: changed-files.txt ==" in out
    assert "tracked.txt" in out
    assert "new.txt" in out
    assert "== report: changed-files status ==" in out
    assert (" M tracked.txt" in out) or ("AM tracked.txt" in out)
    assert "?? new.txt" in out
    assert "== report: changed-files diff stat ==" in out
