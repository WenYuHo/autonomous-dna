import json
from pathlib import Path
from unittest.mock import patch

from autodna.core import repo_hooks


def _write_contract(repo_root: Path, stages: dict) -> Path:
    contract_path = repo_root / "tools" / "repo_hooks.json"
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(json.dumps({"version": 1, "stages": stages}, indent=2), encoding="utf-8")
    return contract_path


def test_run_hook_stage_uses_repo_contract_and_writes_manifest(tmp_path):
    repo_root = tmp_path
    _write_contract(
        repo_root,
        {
            "repo_setup": [
                {"name": "guard", "command": ["python", "tools/guard_scaffold.py", "--check"], "timeout": 30},
                {"name": "session", "command": ["python", "tools/session_start.py"], "timeout": 45},
            ]
        },
    )

    calls = []

    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None, shell=None):
        calls.append({"cmd": cmd, "cwd": cwd, "timeout": timeout, "shell": shell})
        return type("Result", (), {"returncode": 0, "stdout": f"ran {cmd[-1]}", "stderr": ""})()

    with patch("autodna.core.repo_hooks.subprocess.run", side_effect=fake_run), patch(
        "autodna.core.repo_hooks.sys.executable", "python"
    ):
        result = repo_hooks.run_hook_stage(repo_root=repo_root, stage="repo_setup")

    assert result["ok"] is True
    assert result["status"] == "passed"
    assert [hook["name"] for hook in result["hooks"]] == ["guard", "session"]
    assert calls[0]["cmd"] == ["python", "tools/guard_scaffold.py", "--check"]
    assert calls[1]["cmd"] == ["python", "tools/session_start.py"]

    manifest_path = Path(result["manifest_path"])
    assert manifest_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["stage"] == "repo_setup"
    assert [hook["name"] for hook in manifest["hooks"]] == ["guard", "session"]
    assert manifest["contract_path"] == str(repo_root / "tools" / "repo_hooks.json")


def test_run_hook_stage_stops_on_first_failure(tmp_path):
    repo_root = tmp_path
    _write_contract(
        repo_root,
        {
            "repo_verification": [
                {"name": "tests", "command": ["python", "-m", "pytest", "tests", "-v"], "timeout": 300},
                {"name": "dogfood", "command": ["python", "-m", "autodna.cli", "user_dogfood"], "timeout": 300},
            ]
        },
    )

    calls = []

    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None, shell=None):
        calls.append(cmd)
        return type("Result", (), {"returncode": 1, "stdout": "", "stderr": "boom"})()

    with patch("autodna.core.repo_hooks.subprocess.run", side_effect=fake_run), patch(
        "autodna.core.repo_hooks.sys.executable", "python"
    ):
        result = repo_hooks.run_hook_stage(repo_root=repo_root, stage="repo_verification")

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert [hook["name"] for hook in result["hooks"]] == ["tests"]
    assert calls == [["python", "-m", "pytest", "tests", "-v"]]

