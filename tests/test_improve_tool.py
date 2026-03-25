"""
tests/test_improve_tool.py
Unit tests for autodna/tools/improve.py helpers.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from autodna.tools.improve import (
    compare_and_gate,
    ensure_clean_working_tree,
    execute_improve,
    run_command,
    run_user_dogfood_gate,
)


def test_ensure_clean_working_tree_raises_on_dirty():
    class Result:
        stdout = " M dirty.txt\n"

    with patch("subprocess.run", return_value=Result()):
        with pytest.raises(SystemExit):
            ensure_clean_working_tree()


def test_run_command_success():
    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    with patch("subprocess.run", return_value=Result()):
        ok, out, err = run_command(["echo", "ok"], timeout=1, shell=False)
        assert ok is True
        assert out == "ok"
        assert err == ""


def test_compare_and_gate_detects_failure(tmp_path):
    baseline = tmp_path / "baseline.md"
    after = tmp_path / "after.md"

    baseline.write_text(
        "# Dogfood Report\n"
        "- Memory facts: 10\n"
        "- Task counts: in_progress=1, backlog=1, done=1\n",
        encoding="utf-8",
    )
    after.write_text(
        "# Dogfood Report\n"
        "- Memory facts: 12\n"
        "- Task counts: in_progress=2, backlog=3, done=2\n",
        encoding="utf-8",
    )

    failures, _summary = compare_and_gate(
        baseline_path=baseline,
        after_path=after,
        gates=["backlog_delta<=0"],
        use_default_gates=False,
    )
    assert any("backlog_delta<=0" in failure for failure in failures)


def test_run_user_dogfood_gate_skips_when_requested():
    result = run_user_dogfood_gate(Path("."), allow_skip=True)
    assert result["ok"] is True
    assert result["skipped"] is True


def _make_improve_args(**overrides):
    defaults = {
        "apply_cmd": ["python -c \"print('apply ok')\""],
        "apply_shell": False,
        "apply_timeout": 60,
        "test_cmd": None,
        "test_timeout": 300,
        "skip_tests": False,
        "skip_user_dogfood": True,
        "baseline_label": "baseline",
        "after_label": "after",
        "notes": "",
        "include_benchmark": False,
        "target_dir": ".",
        "out_dir": "agent/dogfood_reports",
        "gate": [],
        "no_default_gates": False,
        "allow_dirty": True,
        "no_revert": True,
        "dry_run": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _hook_result(tmp_path: Path, stage: str, ok: bool = True) -> dict:
    manifest_path = tmp_path / "agent" / "reports" / f"{stage}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"stage": stage, "ok": ok}, indent=2), encoding="utf-8")
    return {
        "ok": ok,
        "status": "passed" if ok else "failed",
        "stage": stage,
        "manifest_path": str(manifest_path),
        "hooks": [{"name": stage, "ok": ok}],
    }


def test_execute_improve_runs_shared_hooks_and_writes_artifact(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    baseline_path = tmp_path / "agent" / "dogfood_reports" / "baseline.md"
    after_path = tmp_path / "agent" / "dogfood_reports" / "after.md"
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text("baseline\n", encoding="utf-8")
    after_path.write_text("after\n", encoding="utf-8")
    args = _make_improve_args()
    hook_calls = []

    def fake_run_hook_stage(*, repo_root, stage, **_kwargs):
        hook_calls.append(stage)
        return _hook_result(tmp_path, stage, ok=True)

    with patch("autodna.tools.improve.generate_report", side_effect=[baseline_path, after_path]), patch(
        "autodna.tools.improve.run_command", return_value=(True, "ok", "")
    ), patch("autodna.tools.improve.compare_and_gate", return_value=([], "summary")), patch(
        "autodna.tools.improve.run_user_dogfood_gate",
        return_value={"ok": True, "status": "skipped", "skipped": True, "artifacts": {}},
    ), patch("autodna.tools.improve.repo_hooks.run_hook_stage", side_effect=fake_run_hook_stage):
        result = execute_improve(args)

    assert result["status"] == "passed"
    assert hook_calls == ["repo_setup", "repo_verification"]
    artifact_path = Path(result["artifact_path"])
    assert artifact_path.exists()
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["hook_runs"]["repo_setup"]["status"] == "passed"
    assert artifact["hook_runs"]["repo_verification"]["status"] == "passed"
    assert artifact["baseline_report"] == str(baseline_path)
    assert artifact["after_report"] == str(after_path)


def test_execute_improve_stops_when_verification_hooks_fail(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    baseline_path = tmp_path / "agent" / "dogfood_reports" / "baseline.md"
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text("baseline\n", encoding="utf-8")
    args = _make_improve_args()

    def fake_run_hook_stage(*, repo_root, stage, **_kwargs):
        return _hook_result(tmp_path, stage, ok=stage != "repo_verification")

    with patch("autodna.tools.improve.generate_report", return_value=baseline_path), patch(
        "autodna.tools.improve.run_command", return_value=(True, "ok", "")
    ), patch("autodna.tools.improve.run_user_dogfood_gate") as mock_dogfood, patch(
        "autodna.tools.improve.repo_hooks.run_hook_stage", side_effect=fake_run_hook_stage
    ):
        result = execute_improve(args)

    assert result["status"] == "failed"
    assert result["error"] == "repo verification hooks failed"
    assert Path(result["artifact_path"]).exists()
    mock_dogfood.assert_not_called()
