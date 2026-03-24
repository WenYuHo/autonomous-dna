import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _ignore_patterns() -> callable:
    return shutil.ignore_patterns(
        ".git",
        "__pycache__",
        "*.pyc",
        ".pytest_cache",
        "agent/user_dogfood_*",
        "agent/dogfood_reports",
        "agent/reports",
        "agent/traces",
    )


def _run_command(cmd: list[str], cwd: Path, timeout: int) -> tuple[int, str, str]:
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )
    return result.returncode, result.stdout or "", result.stderr or ""


def _step_record(
    *,
    name: str,
    cmd: list[str],
    cwd: Path,
    timeout: int,
    artifact_dir: Path,
) -> dict:
    returncode, stdout, stderr = _run_command(cmd, cwd=cwd, timeout=timeout)
    stdout_path = artifact_dir / f"{name}.stdout.txt"
    stderr_path = artifact_dir / f"{name}.stderr.txt"
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    return {
        "name": name,
        "command": cmd,
        "cwd": str(cwd),
        "timeout": timeout,
        "returncode": returncode,
        "ok": returncode == 0,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "stdout": stdout,
        "stderr": stderr,
    }


def _copy_log_if_present(temp_project: Path, artifact_dir: Path, agent_name: str) -> str | None:
    log_path = temp_project / "agent" / f"{agent_name}.log"
    if not log_path.exists():
        return None
    copied = artifact_dir / f"{agent_name}.log.txt"
    copied.write_text(log_path.read_text(encoding="utf-8"), encoding="utf-8")
    return str(copied)


def run_user_dogfood_flow(
    repo_root: Path | str | None = None,
    *,
    temp_parent: Path | str | None = None,
    artifact_parent: Path | str | None = None,
    agent_name: str = "user-dogfood",
    mission: str = "User dogfood smoke mission",
    bootstrap_timeout: int = 300,
    bridge_timeout: int = 120,
    session_timeout: int = 120,
    git_init_timeout: int = 60,
    smoke_timeout: int = 120,
    keep_temp: bool = False,
) -> dict:
    repo_root_path = Path(repo_root or Path.cwd()).resolve()
    temp_parent_path = Path(temp_parent).resolve() if temp_parent else None
    artifact_parent_path = Path(artifact_parent).resolve() if artifact_parent else None
    timestamp = _now_stamp()

    temp_project = Path(
        tempfile.mkdtemp(
            prefix="autodna-user-dogfood-project-",
            dir=str(temp_parent_path) if temp_parent_path else None,
        )
    )
    artifact_dir = Path(
        tempfile.mkdtemp(
            prefix="autodna-user-dogfood-artifacts-",
            dir=str(artifact_parent_path) if artifact_parent_path else None,
        )
    )

    steps: list[dict] = []
    smoke_log_path: str | None = None
    error: str | None = None

    try:
        shutil.copytree(repo_root_path, temp_project, dirs_exist_ok=True, ignore=_ignore_patterns())

        bootstrap_script = temp_project / "scripts" / "bootstrap.py"
        bridge_script = temp_project / "bridge.py"
        session_script = temp_project / "tools" / "session_start.py"

        steps.append(
            _step_record(
                name="bootstrap",
                cmd=[sys.executable, str(bootstrap_script)],
                cwd=temp_project,
                timeout=bootstrap_timeout,
                artifact_dir=artifact_dir,
            )
        )
        if not steps[-1]["ok"]:
            error = "bootstrap failed"
            return _finalize_user_dogfood_result(
                repo_root_path,
                temp_project,
                artifact_dir,
                steps,
                smoke_log_path,
                error,
                timestamp,
                keep_temp,
            )

        steps.append(
            _step_record(
                name="bridge",
                cmd=[sys.executable, str(bridge_script)],
                cwd=temp_project,
                timeout=bridge_timeout,
                artifact_dir=artifact_dir,
            )
        )
        if not steps[-1]["ok"]:
            error = "bridge failed"
            return _finalize_user_dogfood_result(
                repo_root_path,
                temp_project,
                artifact_dir,
                steps,
                smoke_log_path,
                error,
                timestamp,
                keep_temp,
            )

        steps.append(
            _step_record(
                name="session_start",
                cmd=[sys.executable, str(session_script)],
                cwd=temp_project,
                timeout=session_timeout,
                artifact_dir=artifact_dir,
            )
        )
        if not steps[-1]["ok"]:
            error = "session_start failed"
            return _finalize_user_dogfood_result(
                repo_root_path,
                temp_project,
                artifact_dir,
                steps,
                smoke_log_path,
                error,
                timestamp,
                keep_temp,
            )

        steps.append(
            _step_record(
                name="git_init",
                cmd=["git", "init", "-q"],
                cwd=temp_project,
                timeout=git_init_timeout,
                artifact_dir=artifact_dir,
            )
        )
        if not steps[-1]["ok"]:
            error = "git init failed"
            return _finalize_user_dogfood_result(
                repo_root_path,
                temp_project,
                artifact_dir,
                steps,
                smoke_log_path,
                error,
                timestamp,
                keep_temp,
            )

        smoke_cmd = [
            sys.executable,
            "-m",
            "autodna.cli",
            "start",
            "--headless",
            "--agent-name",
            agent_name,
            "--mission",
            mission,
        ]
        steps.append(
            _step_record(
                name="smoke_start",
                cmd=smoke_cmd,
                cwd=temp_project,
                timeout=smoke_timeout,
                artifact_dir=artifact_dir,
            )
        )
        smoke_log_path = _copy_log_if_present(temp_project, artifact_dir, agent_name)
        if smoke_log_path:
            steps[-1]["smoke_log_path"] = smoke_log_path
        if not steps[-1]["ok"]:
            error = "smoke start failed"

    except Exception as exc:  # pragma: no cover - defensive fallback
        error = f"{type(exc).__name__}: {exc}"
    finally:
        manifest_path = artifact_dir / "manifest.json"
        result = _finalize_user_dogfood_result(
            repo_root_path,
            temp_project,
            artifact_dir,
            steps,
            smoke_log_path,
            error,
            timestamp,
            keep_temp,
        )
        manifest_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    return result


def _finalize_user_dogfood_result(
    repo_root: Path,
    temp_project: Path,
    artifact_dir: Path,
    steps: list[dict],
    smoke_log_path: str | None,
    error: str | None,
    timestamp: str,
    keep_temp: bool,
) -> dict:
    ok = error is None and all(step.get("ok") for step in steps)
    result = {
        "ok": ok,
        "status": "passed" if ok else "failed",
        "timestamp": timestamp,
        "repo_root": str(repo_root),
        "temp_project": str(temp_project),
        "artifact_dir": str(artifact_dir),
        "smoke_log_path": smoke_log_path,
        "error": error,
        "steps": steps,
        "artifacts": {
            "manifest": str(artifact_dir / "manifest.json"),
        },
    }
    for step in steps:
        result["artifacts"][f"{step['name']}_stdout"] = step["stdout_path"]
        result["artifacts"][f"{step['name']}_stderr"] = step["stderr_path"]
        if "smoke_log_path" in step:
            result["artifacts"]["smoke_log"] = step["smoke_log_path"]
    if not keep_temp:
        shutil.rmtree(temp_project, ignore_errors=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the target-repo user dogfood verification flow")
    parser.add_argument("--repo-root", default=".", help="Repository root to validate")
    parser.add_argument("--temp-parent", help="Directory where the temporary project should be created")
    parser.add_argument("--artifact-parent", help="Directory where artifacts should be stored")
    parser.add_argument("--agent-name", default="user-dogfood", help="Agent name for the smoke launch")
    parser.add_argument("--mission", default="User dogfood smoke mission", help="Mission for the smoke launch")
    parser.add_argument("--keep-temp", action="store_true", help="Keep the temporary project for inspection")
    args = parser.parse_args()

    result = run_user_dogfood_flow(
        repo_root=args.repo_root,
        temp_parent=args.temp_parent,
        artifact_parent=args.artifact_parent,
        agent_name=args.agent_name,
        mission=args.mission,
        keep_temp=args.keep_temp,
    )
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
