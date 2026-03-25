import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


CONTRACT_RELATIVE_PATH = Path("tools") / "repo_hooks.json"
DEFAULT_CONTRACT = {
    "version": 1,
    "stages": {
        "bootstrap_setup": [
            {"name": "bridge", "command": ["python", "bridge.py"], "timeout": 120},
            {"name": "session_start", "command": ["python", "tools/session_start.py"], "timeout": 120},
        ],
        "repo_setup": [
            {"name": "guard_scaffold", "command": ["python", "tools/guard_scaffold.py", "--check"], "timeout": 60},
        ],
        "repo_verification": [
            {"name": "pytest", "command": ["python", "-m", "pytest", "tests", "-v"], "timeout": 1800},
        ],
    },
}


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _safe_slug(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value).strip("-") or "hook"


def load_hook_contract(repo_root: Path | str) -> tuple[dict, Path, str]:
    repo_root_path = Path(repo_root).resolve()
    contract_path = repo_root_path / CONTRACT_RELATIVE_PATH
    if contract_path.exists():
        return json.loads(contract_path.read_text(encoding="utf-8")), contract_path, "repo"
    return json.loads(json.dumps(DEFAULT_CONTRACT)), contract_path, "default"


def _artifact_root(repo_root: Path, artifact_parent: Path | str | None) -> Path:
    if artifact_parent:
        root = Path(artifact_parent).resolve()
    else:
        root = repo_root / "agent" / "reports" / "hook_runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _normalize_command(command, shell: bool):
    if isinstance(command, str):
        if shell:
            return command
        normalized = shlex.split(command, posix=(os.name != "nt"))
    else:
        normalized = list(command)

    if not shell and normalized and normalized[0] == "python":
        normalized[0] = sys.executable
    return normalized


def _resolve_cwd(repo_root: Path, hook: dict) -> Path:
    cwd_value = hook.get("cwd", ".")
    cwd_path = Path(cwd_value)
    if cwd_path.is_absolute():
        return cwd_path
    return repo_root / cwd_path


def _run_hook(repo_root: Path, artifact_root: Path, stage: str, index: int, hook: dict) -> dict:
    name = hook.get("name") or f"{stage}_{index}"
    timeout = int(hook.get("timeout", 120))
    shell = bool(hook.get("shell", False))
    command = _normalize_command(hook["command"], shell=shell)
    cwd = _resolve_cwd(repo_root, hook)
    slug = _safe_slug(name)
    stdout_path = artifact_root / f"{stage}_{index:02d}_{slug}.stdout.txt"
    stderr_path = artifact_root / f"{stage}_{index:02d}_{slug}.stderr.txt"

    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=shell,
        )
        returncode = completed.returncode
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except subprocess.TimeoutExpired as exc:
        returncode = None
        stdout = exc.stdout or ""
        stderr = exc.stderr or f"Timed out after {timeout} seconds"
    except Exception as exc:  # pragma: no cover - defensive fallback
        returncode = None
        stdout = ""
        stderr = f"{type(exc).__name__}: {exc}"

    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")

    return {
        "name": name,
        "index": index,
        "command": command,
        "cwd": str(cwd),
        "timeout": timeout,
        "shell": shell,
        "returncode": returncode,
        "ok": returncode == 0,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def run_hook_stage(
    *,
    repo_root: Path | str,
    stage: str,
    artifact_parent: Path | str | None = None,
    override_hooks: list[dict] | None = None,
) -> dict:
    repo_root_path = Path(repo_root).resolve()
    contract, contract_path, contract_source = load_hook_contract(repo_root_path)
    hooks = override_hooks if override_hooks is not None else contract.get("stages", {}).get(stage, [])
    artifact_root = _artifact_root(repo_root_path, artifact_parent)
    timestamp = _now_stamp()
    manifest_path = artifact_root / f"{stage}_{timestamp}.json"

    records: list[dict] = []
    for index, hook in enumerate(hooks, start=1):
        record = _run_hook(repo_root_path, artifact_root, stage, index, hook)
        records.append(record)
        if not record["ok"]:
            break

    ok = all(record.get("ok") for record in records)
    status = "skipped" if not hooks else ("passed" if ok and len(records) == len(hooks) else "failed")
    result = {
        "ok": True if not hooks else ok,
        "status": status,
        "stage": stage,
        "timestamp": timestamp,
        "repo_root": str(repo_root_path),
        "contract_path": str(contract_path),
        "contract_source": contract_source,
        "manifest_path": str(manifest_path),
        "hooks": records,
    }
    manifest_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
