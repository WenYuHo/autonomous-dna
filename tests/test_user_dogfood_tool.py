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

    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None, shell=None):
        cwd_path = Path(cwd)
        if len(cmd) >= 2 and str(cmd[1]).endswith("bootstrap.py"):
            return type("Result", (), {"returncode": 0, "stdout": "bootstrap ok", "stderr": ""})()
        if len(cmd) >= 2 and str(cmd[1]).endswith("bridge.py"):
            return type("Result", (), {"returncode": 0, "stdout": "bridge ok", "stderr": ""})()
        if len(cmd) >= 2 and str(cmd[1]).endswith("session_start.py"):
            return type("Result", (), {"returncode": 0, "stdout": "session ok", "stderr": ""})()
        if cmd[:3] == ["git", "init", "-q"]:
            return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        if len(cmd) >= 4 and cmd[:3] == ["python", "-m", "autodna.cli"]:
            log_path = cwd_path / "agent" / "user-dogfood.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("launch ok\n", encoding="utf-8")
            return type("Result", (), {"returncode": 0, "stdout": f"Log: {log_path}", "stderr": ""})()
        raise AssertionError(f"Unexpected command: {cmd}")

    with patch("autodna.tools.user_dogfood.sys.executable", "python"), patch(
        "autodna.tools.user_dogfood.subprocess.run", side_effect=fake_run
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
    assert any(step["name"] == "smoke_start" for step in result["steps"])


def test_run_user_dogfood_flow_fails_on_bridge(tmp_path):
    source_root = _make_source_repo(tmp_path)
    artifact_parent = tmp_path / "artifacts"
    artifact_parent.mkdir()

    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None, shell=None):
        if len(cmd) >= 2 and str(cmd[1]).endswith("bootstrap.py"):
            return type("Result", (), {"returncode": 0, "stdout": "bootstrap ok", "stderr": ""})()
        if len(cmd) >= 2 and str(cmd[1]).endswith("bridge.py"):
            return type("Result", (), {"returncode": 1, "stdout": "bridge fail", "stderr": "boom"})()
        raise AssertionError(f"Unexpected command: {cmd}")

    with patch("autodna.tools.user_dogfood.sys.executable", "python"), patch(
        "autodna.tools.user_dogfood.subprocess.run", side_effect=fake_run
    ):
        result = run_user_dogfood_flow(
            repo_root=source_root,
            temp_parent=tmp_path,
            artifact_parent=artifact_parent,
            keep_temp=False,
        )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["error"] == "bridge failed"
    assert [step["name"] for step in result["steps"]] == ["bootstrap", "bridge"]
