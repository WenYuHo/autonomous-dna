import json
from pathlib import Path
from unittest.mock import patch

from autodna.tools.user_dogfood import run_user_dogfood_flow


def _make_source_repo(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    (source / "scripts").mkdir(parents=True)
    (source / "tools").mkdir(parents=True)
    (source / "autodna" / "core").mkdir(parents=True)
    (source / "agent").mkdir(parents=True)

    (source / "scripts" / "bootstrap.py").write_text("print('bootstrap')\n", encoding="utf-8")
    (source / "bridge.py").write_text("print('bridge')\n", encoding="utf-8")
    (source / "tools" / "session_start.py").write_text("print('session start')\n", encoding="utf-8")
    (source / "autodna" / "__init__.py").write_text("", encoding="utf-8")
    (source / "autodna" / "cli.py").write_text("print('cli')\n", encoding="utf-8")
    (source / "autodna" / "core" / "__init__.py").write_text("", encoding="utf-8")
    (source / "autodna" / "core" / "engine_start.py").write_text("print('engine start')\n", encoding="utf-8")
    return source


def test_run_user_dogfood_flow_success(tmp_path):
    source_root = _make_source_repo(tmp_path)
    artifact_parent = tmp_path / "artifacts"
    artifact_parent.mkdir()

    def fake_run_hook_stage(*, repo_root, stage, artifact_parent=None, **_kwargs):
        manifest_path = Path(artifact_parent) / f"{stage}.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "stage": stage,
                    "ok": True,
                    "status": "passed",
                    "hooks": [
                        {"name": "bridge", "ok": True},
                        {"name": "session_start", "ok": True},
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return {
            "ok": True,
            "status": "passed",
            "stage": stage,
            "manifest_path": str(manifest_path),
            "hooks": [
                {"name": "bridge", "ok": True},
                {"name": "session_start", "ok": True},
            ],
        }

    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None, shell=None):
        cwd_path = Path(cwd)
        if len(cmd) >= 2 and str(cmd[1]).endswith("bootstrap.py"):
            return type("Result", (), {"returncode": 0, "stdout": "bootstrap ok", "stderr": ""})()
        if cmd[:3] == ["git", "init", "-q"]:
            return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        if len(cmd) >= 4 and cmd[:3] == ["python", "-m", "autodna.cli"]:
            hook_dir = cwd_path / "agent" / "reports" / "hook_runs"
            hook_dir.mkdir(parents=True, exist_ok=True)
            (hook_dir / "repo_setup_20260325T000000Z.json").write_text(
                json.dumps(
                    {
                        "stage": "repo_setup",
                        "ok": True,
                        "status": "passed",
                        "hooks": [{"name": "guard_scaffold", "ok": True}],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            log_path = cwd_path / "agent" / "user-dogfood.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("launch ok\n", encoding="utf-8")
            return type("Result", (), {"returncode": 0, "stdout": f"Log: {log_path}", "stderr": ""})()
        raise AssertionError(f"Unexpected command: {cmd}")

    with patch("autodna.tools.user_dogfood.sys.executable", "python"), patch(
        "autodna.tools.user_dogfood.subprocess.run", side_effect=fake_run
    ), patch(
        "autodna.tools.user_dogfood.repo_hooks.run_hook_stage", side_effect=fake_run_hook_stage
    ):
        result = run_user_dogfood_flow(
            repo_root=source_root,
            temp_parent=tmp_path,
            artifact_parent=artifact_parent,
            keep_temp=False,
        )

    assert result["ok"] is True
    assert result["status"] == "passed"
    assert result["artifact_dir"].startswith(str(artifact_parent))
    assert result["smoke_log_path"] is not None
    assert Path(result["artifacts"]["manifest"]).exists()
    assert result["artifacts"]["bootstrap_setup_manifest"].endswith("bootstrap_setup.json")
    assert result["artifacts"]["smoke_repo_setup_manifest"].endswith(".json")
    assert result["hook_runs"]["bootstrap_setup"]["status"] == "passed"
    assert result["hook_runs"]["smoke_repo_setup"]["status"] == "passed"
    assert any(step["name"] == "smoke_start" for step in result["steps"])


def test_run_user_dogfood_flow_fails_on_bootstrap_hooks(tmp_path):
    source_root = _make_source_repo(tmp_path)
    artifact_parent = tmp_path / "artifacts"
    artifact_parent.mkdir()

    def fake_run_hook_stage(*, repo_root, stage, artifact_parent=None, **_kwargs):
        manifest_path = Path(artifact_parent) / f"{stage}.json"
        manifest_path.write_text(
            json.dumps({"stage": stage, "ok": False, "status": "failed"}, indent=2),
            encoding="utf-8",
        )
        return {
            "ok": False,
            "status": "failed",
            "stage": stage,
            "manifest_path": str(manifest_path),
            "hooks": [{"name": "bridge", "ok": False}],
        }

    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None, shell=None):
        if len(cmd) >= 2 and str(cmd[1]).endswith("bootstrap.py"):
            return type("Result", (), {"returncode": 0, "stdout": "bootstrap ok", "stderr": ""})()
        raise AssertionError(f"Unexpected command: {cmd}")

    with patch("autodna.tools.user_dogfood.sys.executable", "python"), patch(
        "autodna.tools.user_dogfood.subprocess.run", side_effect=fake_run
    ), patch(
        "autodna.tools.user_dogfood.repo_hooks.run_hook_stage", side_effect=fake_run_hook_stage
    ):
        result = run_user_dogfood_flow(
            repo_root=source_root,
            temp_parent=tmp_path,
            artifact_parent=artifact_parent,
            keep_temp=False,
        )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["error"] == "bootstrap_setup hooks failed"
    assert [step["name"] for step in result["steps"]] == ["bootstrap", "bootstrap_setup"]
