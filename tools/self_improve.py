"""
tools/self_improve.py
Orchestrator for the Autonomous-DNA self-improvement loop.
Allows the agent swarm to work on its own repository autonomously.

Usage:
  python tools/self_improve.py [--dry-run]
"""

import argparse
import json
import logging
import os
import subprocess
import shutil
import sys
import time
from datetime import datetime, timezone, timedelta
import re
import queue
import threading
from pathlib import Path

from autodna.tools import dogfood

# Setup basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Enforce UTF-8 for stdout/stderr on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

TASK_QUEUE_FILE = Path("agent/TASK_QUEUE.json")
DEFAULT_BASE_BRANCHES = ("dev", "main", "master")
UNBLOCKED_STATUSES = {"done", "info", "completed"}
DEFAULT_RESEARCH_TOPICS = [
    "latest state of the art AI coding agent system prompts and framework architecture 2026",
    "ai coding agent eval harnesses, regression gates, and benchmark suites 2025 2026",
    "tool-use reliability, prompt injection defenses, and guardrails for coding agents",
]
RESEARCH_TIMEOUT_SECONDS = 300
TASKGEN_TIMEOUT_SECONDS = 120
EVAL_TIMEOUT_SECONDS = 120
HEARTBEAT_TTL_SECONDS = int(os.getenv("AUTODNA_TASK_HEARTBEAT_TTL", "900"))
DIRTY_POLICY_DEFAULT = "stash"
DIRTY_POLICY_KEEP = "keep"
DIRTY_POLICY_SKIP = "skip"
DIRTY_POLICY_STASH = "stash"
DIRTY_POLICY_COMMIT = "commit"
WORKER_NAMES = ("worker-1", "worker-2")

from typing import Any, Dict, Optional

def _run_git_command(args: list[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd) if cwd else None,
    )


def working_tree_is_clean() -> bool:
    """Check git working tree status without mutating state."""
    result = _run_git_command(["git", "status", "--porcelain"])
    return not result.stdout.strip()


def _latest_stash_ref() -> Optional[str]:
    result = _run_git_command(["git", "stash", "list", "-n", "1", "--format=%gd"])
    if result.returncode != 0:
        return None
    ref = result.stdout.strip()
    return ref or None


def stash_working_tree() -> Optional[str]:
    """Stash all changes (including untracked) and return the stash ref."""
    if working_tree_is_clean():
        return None
    message = f"autodna-self-improve-{int(time.time())}"
    result = _run_git_command(["git", "stash", "push", "-u", "-m", message])
    if result.returncode != 0:
        logger.warning("Failed to stash working tree changes.")
        if result.stdout:
            logger.warning(result.stdout.strip()[-1000:])
        if result.stderr:
            logger.warning(result.stderr.strip()[-1000:])
        return None
    return _latest_stash_ref()


def _current_git_ref() -> str:
    result = _run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if result.returncode == 0:
        ref = result.stdout.strip()
        if ref and ref != "HEAD":
            return ref
    sha = _run_git_command(["git", "rev-parse", "HEAD"])
    if sha.returncode == 0:
        return sha.stdout.strip()
    return "HEAD"


def commit_dirty_working_tree() -> bool:
    """Commit dirty changes onto a backup branch and return to the original ref."""
    if working_tree_is_clean():
        return True
    original_ref = _current_git_ref()
    backup_branch = f"chore/self-improve-dirty-{int(time.time())}"
    checkout = _run_git_command(["git", "checkout", "-b", backup_branch])
    if checkout.returncode != 0:
        logger.warning("Failed to create backup branch for dirty changes.")
        return False

    add = _run_git_command(["git", "add", "-A"])
    if add.returncode != 0:
        logger.warning("Failed to stage dirty changes for backup commit.")
        _run_git_command(["git", "checkout", original_ref])
        return False

    commit = _run_git_command(["git", "commit", "-m", "chore: autosave self-improve working tree"])
    if commit.returncode != 0:
        logger.warning("Failed to commit dirty changes for backup.")
        if commit.stdout:
            logger.warning(commit.stdout.strip()[-1000:])
        if commit.stderr:
            logger.warning(commit.stderr.strip()[-1000:])
        _run_git_command(["git", "checkout", original_ref])
        return False

    logger.info(f"Saved dirty working tree to backup branch {backup_branch}.")
    _run_git_command(["git", "checkout", original_ref])
    return True


def restore_stash(stash_ref: Optional[str]) -> bool:
    """Re-apply and drop the given stash ref."""
    if not stash_ref:
        return True
    apply_result = _run_git_command(["git", "stash", "apply", "--index", stash_ref])
    if apply_result.returncode != 0:
        logger.warning(f"Failed to re-apply stash {stash_ref}. Manual resolution required.")
        if apply_result.stdout:
            logger.warning(apply_result.stdout.strip()[-1000:])
        if apply_result.stderr:
            logger.warning(apply_result.stderr.strip()[-1000:])
        return False
    drop_result = _run_git_command(["git", "stash", "drop", stash_ref])
    if drop_result.returncode != 0:
        logger.warning(f"Failed to drop stash {stash_ref} after apply.")
        if drop_result.stdout:
            logger.warning(drop_result.stdout.strip()[-1000:])
        if drop_result.stderr:
            logger.warning(drop_result.stderr.strip()[-1000:])
        return False
    return True


def handle_dirty_working_tree(policy: str) -> tuple[bool, Optional[str]]:
    """Handle a dirty working tree based on policy. Returns (proceed, stash_ref)."""
    if working_tree_is_clean():
        return True, None

    normalized = (policy or DIRTY_POLICY_DEFAULT).strip().lower()
    if normalized == DIRTY_POLICY_SKIP:
        logger.warning("Working tree is not clean. Skipping self-improve.")
        return False, None
    if normalized == DIRTY_POLICY_COMMIT:
        if commit_dirty_working_tree():
            return True, None
        logger.warning("Commit policy failed. Falling back to stash.")
        normalized = DIRTY_POLICY_STASH
    if normalized != DIRTY_POLICY_STASH:
        logger.warning(f"Unknown dirty policy '{policy}'. Falling back to stash.")
        normalized = DIRTY_POLICY_STASH

    stash_ref = stash_working_tree()
    if stash_ref:
        return True, stash_ref
    if working_tree_is_clean():
        return True, None
    logger.warning("Failed to stash dirty working tree. Skipping self-improve.")
    return False, None

def _bool_env(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes"}


def _ensure_safe_directory(path: Path) -> None:
    if _bool_env("AUTODNA_WORKTREE_SAFE_DIRECTORY", "1") or _bool_env("AUTODNA_GIT_SAFE_DIRECTORY", "0"):
        _run_git_command(["git", "config", "--global", "--add", "safe.directory", str(path.resolve())])


def _is_worktree_dir(path: Path) -> bool:
    git_path = path / ".git"
    return git_path.is_file() or git_path.is_dir()


def _worktree_has_changes(path: Path) -> bool:
    _ensure_safe_directory(path)
    result = _run_git_command(["git", "status", "--porcelain"], cwd=path)
    return result.returncode == 0 and bool(result.stdout.strip())


def _stash_worktree(path: Path) -> bool:
    _ensure_safe_directory(path)
    message = f"autodna-self-improve-worktree-{path.name}-{int(time.time())}"
    result = _run_git_command(["git", "stash", "push", "-u", "-m", message], cwd=path)
    if result.returncode != 0:
        logger.warning(f"Failed to stash changes in {path}.")
        if result.stdout:
            logger.warning(result.stdout.strip()[-1000:])
        if result.stderr:
            logger.warning(result.stderr.strip()[-1000:])
        return False
    return True


def _commit_worktree(path: Path) -> bool:
    _ensure_safe_directory(path)
    add = _run_git_command(["git", "add", "-A"], cwd=path)
    if add.returncode != 0:
        logger.warning(f"Failed to stage changes in {path}.")
        return False
    diff = _run_git_command(["git", "diff", "--cached", "--quiet"], cwd=path)
    if diff.returncode == 0:
        return True
    message = f"chore: snapshot worktree {path.name}"
    commit = _run_git_command(["git", "commit", "-m", message], cwd=path)
    if commit.returncode != 0:
        logger.warning(f"Failed to commit changes in {path}.")
        if commit.stdout:
            logger.warning(commit.stdout.strip()[-1000:])
        if commit.stderr:
            logger.warning(commit.stderr.strip()[-1000:])
        return False
    return True


def _handle_dirty_worktree(path: Path, policy: Optional[str]) -> bool:
    normalized = (policy or DIRTY_POLICY_COMMIT).strip().lower()
    if normalized == DIRTY_POLICY_KEEP:
        return True
    if normalized == DIRTY_POLICY_SKIP:
        return False
    if normalized == DIRTY_POLICY_STASH:
        return _stash_worktree(path)
    if normalized == DIRTY_POLICY_COMMIT:
        if _commit_worktree(path):
            return True
        logger.warning(f"Failed to commit changes in {path}. Falling back to stash.")
        return _stash_worktree(path)
    logger.warning(f"Unknown worktree dirty policy '{policy}'. Falling back to stash.")
    return _stash_worktree(path)


def _active_workers(tasks: list[Dict[str, Any]]) -> set[str]:
    active = set()
    for task in tasks:
        status = str(task.get("status", "")).lower()
        if status != "in_progress":
            continue
        if not _heartbeat_fresh(task):
            continue
        assigned = task.get("assigned_to")
        if isinstance(assigned, str) and assigned.strip():
            active.add(assigned.strip())
    return active


def _prepare_worker_worktrees(policy: str, repo_root: Path) -> None:
    tasks = _load_tasks()
    active = {name.lower() for name in _active_workers(tasks)}
    for name in WORKER_NAMES:
        path = repo_root / name
        if not path.exists():
            continue
        if not _is_worktree_dir(path):
            logger.warning(f"Skipping {name}: not a git worktree directory.")
            continue
        if name.lower() in active:
            logger.warning(f"Skipping cleanup for {name}; active task heartbeat detected.")
            continue
        if not _worktree_has_changes(path):
            continue
        handled = _handle_dirty_worktree(path, policy)
        if not handled:
            logger.warning(
                f"Worktree {name} has uncommitted changes and policy '{policy}' skipped cleanup."
            )


def parse_gate_env(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def task_snapshot_from_json(queue_path: Path) -> dict:
    if not queue_path.exists():
        return {"last_sync": None, "counts": {"in_progress": 0, "backlog": 0, "done": 0}, "exists": False}
    try:
        data = json.loads(queue_path.read_text(encoding="utf-8"))
    except Exception:
        return {"last_sync": None, "counts": {"in_progress": 0, "backlog": 0, "done": 0}, "exists": False}
    tasks = data.get("tasks", [])
    if not isinstance(tasks, list):
        return {"last_sync": None, "counts": {"in_progress": 0, "backlog": 0, "done": 0}, "exists": False}

    counts = {"in_progress": 0, "backlog": 0, "done": 0}
    for task in tasks:
        status = str(task.get("status", "")).lower()
        if status == "in_progress":
            counts["in_progress"] += 1
        elif status in {"done", "completed", "info"}:
            counts["done"] += 1
        elif status in {"pending", "blocked", "error"}:
            counts["backlog"] += 1
        elif status:
            counts["backlog"] += 1
    return {"last_sync": None, "counts": counts, "exists": True}


def _dogfood_report(label: str, notes: str, out_dir: Path) -> Path:
    repo_root = Path(".").resolve()
    memory_path = Path("agent/MEMORY.md")
    memory_facts = dogfood.count_memory_facts(memory_path)
    task_snapshot = task_snapshot_from_json(Path("agent/TASK_QUEUE.json"))
    if not task_snapshot.get("exists"):
        task_snapshot = dogfood.parse_task_queue(Path("agent/TASK_QUEUE.md"))
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = dogfood.build_report(
        label=label,
        timestamp=timestamp,
        repo_root=repo_root,
        notes=notes,
        memory_facts=memory_facts,
        task_snapshot=task_snapshot,
        benchmark=None,
    )
    return dogfood.write_report(report, out_dir, label, timestamp)


def _evaluate_dogfood(baseline_path: Path, after_path: Path, gates: list[str]) -> tuple[bool, str]:
    if not gates:
        return True, "No dogfood gates configured."
    baseline = dogfood.parse_report(baseline_path)
    after = dogfood.parse_report(after_path)
    deltas = dogfood.compare_reports(baseline, after)
    failures = dogfood.evaluate_gates(after, deltas, gates)
    summary = dogfood.format_compare_summary(
        baseline_path=baseline_path,
        after_path=after_path,
        baseline=baseline,
        after=after,
        deltas=deltas,
        gates=gates,
        failures=failures,
    )
    return not failures, summary

def _load_tasks() -> list[Dict[str, Any]]:
    if not TASK_QUEUE_FILE.exists():
        logger.info(f"{TASK_QUEUE_FILE} not found. No pending tasks to run.")
        return []
    with open(TASK_QUEUE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("tasks", [])


def _task_by_id(tasks: list[Dict[str, Any]]) -> dict[int, Dict[str, Any]]:
    return {t.get("id"): t for t in tasks if isinstance(t.get("id"), int)}


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


def _heartbeat_fresh(task: Dict[str, Any], ttl_seconds: int = HEARTBEAT_TTL_SECONDS) -> bool:
    heartbeat = _parse_iso(task.get("heartbeat_at"))
    if not heartbeat:
        return False
    now = datetime.now(timezone.utc)
    return now - heartbeat <= timedelta(seconds=ttl_seconds)


def _is_blocked(task: Dict[str, Any], by_id: dict[int, Dict[str, Any]]) -> bool:
    blocked_by = task.get("blocked_by")
    if blocked_by is None:
        return False
    blocker = by_id.get(blocked_by)
    if not blocker:
        return False
    status = str(blocker.get("status", "")).lower()
    if status in UNBLOCKED_STATUSES:
        return False
    if status == "in_progress":
        return _heartbeat_fresh(blocker)
    return True


def get_next_task() -> Optional[Dict[str, Any]]:
    """Find the first pending task in TASK_QUEUE.json."""
    tasks = _load_tasks()
    by_id = _task_by_id(tasks)

    for task in tasks:
        status = task.get("status")
        if status != "pending":
            continue
        if task.get("title", "").strip().upper().startswith("CYCLE"):
            continue
        if _is_blocked(task, by_id):
            continue
        logger.info(f"Found pending task: {task['id']} - {task['title']}")
        return task

    logger.info("No pending tasks found.")
    return None


def get_retry_task() -> Optional[Dict[str, Any]]:
    """Find the first retryable error/blocked task whose blockers are resolved."""
    tasks = _load_tasks()
    by_id = _task_by_id(tasks)

    for task in tasks:
        status = task.get("status")
        if status not in {"error", "blocked"}:
            continue
        if task.get("title", "").strip().upper().startswith("CYCLE"):
            continue
        if _is_blocked(task, by_id):
            continue
        logger.info(f"Retrying failed task: {task['id']} - {task['title']}")
        return task

    return None


def _select_actionable_task() -> Optional[Dict[str, Any]]:
    task = get_next_task()
    if task:
        return task

    retry_task = get_retry_task()
    if retry_task:
        update_task_status(retry_task["id"], "pending", "Auto-retry after error.")
        return retry_task

    return None


def select_next_task(always_taskgen: bool) -> Optional[Dict[str, Any]]:
    if always_taskgen:
        _run_taskgen_if_available()

    task = _select_actionable_task()
    if task:
        return task

    if not always_taskgen:
        logger.info("No actionable tasks found. Attempting task generation.")
        if _run_taskgen_if_available():
            return _select_actionable_task()

    return None


def _run_cli_step(command: list[str], label: str, timeout_seconds: int) -> bool:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        logger.warning(f"{label} timed out after {timeout_seconds}s.")
        return False
    except Exception as exc:
        logger.warning(f"{label} failed to launch: {exc}")
        return False

    if result.returncode != 0:
        logger.warning(f"{label} failed (exit code {result.returncode}).")
        if result.stdout:
            logger.warning(result.stdout.strip()[-1000:])
        if result.stderr:
            logger.warning(result.stderr.strip()[-1000:])
        return False
    return True


def _run_taskgen_if_available() -> bool:
    command = [sys.executable, "autodna/cli.py", "taskgen", "--if-empty"]
    return _run_cli_step(command, "Task generation", TASKGEN_TIMEOUT_SECONDS)


def pick_research_topic() -> str:
    env_topic = os.getenv("AUTODNA_SELF_IMPROVE_RESEARCH_TOPIC", "").strip()
    if env_topic:
        return env_topic
    if not DEFAULT_RESEARCH_TOPICS:
        return "latest state of the art AI coding agent system prompts and framework architecture 2026"
    day_index = int(time.time() // 86400) % len(DEFAULT_RESEARCH_TOPICS)
    return DEFAULT_RESEARCH_TOPICS[day_index]


def bootstrap_queue(topic: Optional[str] = None) -> bool:
    chosen_topic = topic or pick_research_topic()
    logger.info("No actionable tasks. Bootstrapping research/taskgen/eval.")
    logger.info(f"Auto-research topic: {chosen_topic}")

    research_ok = _run_cli_step(
        [sys.executable, "autodna/cli.py", "research", "--timestamped", chosen_topic],
        "Auto-research",
        RESEARCH_TIMEOUT_SECONDS,
    )
    if not research_ok:
        logger.warning("Auto-research failed. Continuing.")

    taskgen_ok = _run_cli_step(
        [sys.executable, "autodna/cli.py", "taskgen", "--if-empty"],
        "Auto-taskgen",
        TASKGEN_TIMEOUT_SECONDS,
    )
    if not taskgen_ok:
        logger.warning("Auto-taskgen failed. Continuing.")

    eval_ok = _run_cli_step(
        [sys.executable, "autodna/cli.py", "eval"],
        "Auto-eval",
        EVAL_TIMEOUT_SECONDS,
    )
    if not eval_ok:
        logger.warning("Auto-eval failed. Continuing.")

    return taskgen_ok

def branch_exists(branch_name: str) -> bool:
    refs = [f"refs/heads/{branch_name}", f"refs/remotes/origin/{branch_name}"]
    for ref in refs:
        result = subprocess.run(["git", "show-ref", "--verify", "--quiet", ref])
        if result.returncode == 0:
            return True
    return False

def resolve_base_branch(preferred: Optional[str]) -> str:
    candidates = []
    if preferred:
        candidates.append(preferred)
    candidates.extend(DEFAULT_BASE_BRANCHES)
    for candidate in candidates:
        if not candidate:
            continue
        if branch_exists(candidate):
            return candidate
    return "main"

def update_task_status(task_id: int, new_status: str, notes: Optional[str] = None) -> None:
    """Update task status in TASK_QUEUE.json to prevent infinite loops."""
    if not TASK_QUEUE_FILE.exists():
        return
    with open(TASK_QUEUE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    for task in data.get("tasks", []):
        if task.get("id") == task_id:
            task["status"] = new_status
            if notes:
                task["notes"] = notes
            task["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            break

    with open(TASK_QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def checkout_branch(branch_name: str, base_branch: str) -> None:
    """Check out a new branch or switch if it exists."""
    # Check if branch exists locally
    result = subprocess.run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"], encoding="utf-8", errors="replace")
    if result.returncode == 0:
        logger.info(f"Existing branch found: {branch_name}. Deleting to ensure freshness.")
        subprocess.run(["git", "branch", "-D", branch_name], check=True)

    logger.info(f"Creating new branch from {base_branch}: {branch_name}")
    subprocess.run(["git", "checkout", base_branch], check=True)
    subprocess.run(["git", "checkout", "-b", branch_name], check=True)

def run_tests() -> bool:
    """Run the pytest suite to validate changes."""
    logger.info("Running test suite...")
    result = subprocess.run(["python", "-m", "pytest", "tests/"], capture_output=True, text=True, encoding="utf-8", errors="replace")

    if result.returncode == 0:
        logger.info("Tests passed successfully.")
        return True
    else:
        logger.error(f"Tests failed (exit code {result.returncode})")
        logger.error(result.stdout[-1000:]) # Show last 1000 chars of output
    return False

def _summarize_swarm_failure(output: str) -> Optional[str]:
    if not output:
        return None
    if "ModelNotFoundError" in output or "Requested entity was not found" in output:
        return "Gemini model not found. Update AUTODNA_MODELS or Gemini CLI config."
    if "TerminalQuotaError" in output:
        return "Gemini quota exhausted."
    if "CLI unavailable:" in output:
        return "CLI unavailable. Install the CLI or set AUTODNA_CODEX_CMD."
    if "Permission denied launching CLI" in output or "Access is denied" in output:
        return "CLI permission denied. Fix executable permissions or security policy."
    if "Failed to launch CLI:" in output:
        return "CLI failed to launch. Verify the CLI path and permissions."
    match = re.search(r"exhausted your capacity on this model.*?reset after ([^\\.\\n]+)", output, re.IGNORECASE)
    if match:
        return f"Gemini quota exhausted. Reset after {match.group(1).strip()}."
    if "QUOTA_EXHAUSTED" in output:
        return "Gemini quota exhausted."
    return None


def _detect_codex_env() -> bool:
    if os.environ.get("CODEX_SHELL") == "1":
        return True
    origin = os.environ.get("CODEX_INTERNAL_ORIGINATOR", "")
    if origin and "codex" in origin.lower():
        return True
    if os.environ.get("CODEX_THREAD_ID"):
        return True
    if shutil.which("codex"):
        return True
    return False


def _scan_swarm_log(log_path: Path, offset: int) -> tuple[int, Optional[str]]:
    if not log_path.exists():
        return offset, None
    try:
        with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
            handle.seek(offset)
            chunk = handle.read()
            new_offset = handle.tell()
    except Exception:
        return offset, None

    if not chunk:
        return new_offset, None

    if "AttachConsole failed" in chunk:
        return new_offset, "Gemini CLI console attach failed."
    if "All fallback models exhausted. Cannot continue." in chunk:
        return new_offset, "All configured Gemini models exhausted or unavailable."
    if "TerminalQuotaError" in chunk or "QUOTA_EXHAUSTED" in chunk:
        return new_offset, "Gemini quota exhausted."
    if "ModelNotFoundError" in chunk or "Requested entity was not found" in chunk:
        return new_offset, "Gemini model not found. Update AUTODNA_MODELS or Gemini CLI config."
    if "CLI unavailable:" in chunk:
        return new_offset, "CLI unavailable. Install the CLI or set AUTODNA_CODEX_CMD."
    if "Permission denied launching CLI" in chunk or "Access is denied" in chunk:
        return new_offset, "CLI permission denied. Fix executable permissions."
    if "Failed to launch CLI:" in chunk:
        return new_offset, "CLI failed to launch. Verify the CLI path and permissions."
    return new_offset, None


def _start_output_reader(process: subprocess.Popen) -> queue.Queue:
    output_queue: queue.Queue = queue.Queue()

    def _reader() -> None:
        stdout = process.stdout
        if stdout is None:
            output_queue.put(None)
            return
        for line in iter(stdout.readline, ""):
            output_queue.put(line)
        output_queue.put(None)

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    return output_queue


def _get_task_status(task_id: int) -> tuple[Optional[str], Optional[str]]:
    tasks = _load_tasks()
    for task in tasks:
        if task.get("id") == task_id:
            return task.get("status"), task.get("notes")
    return None, None


def run_swarm(task: Dict[str, Any], timeout_seconds=600) -> tuple[str, Optional[str]]:
    """Spawn the agent swarm and wait for it to finish."""
    logger.info(f"Spawning swarm for task {task['id']} (timeout: {timeout_seconds}s)...")

    try:
        # Pass the task ID so the swarm prioritizes it, and run headlessly
        # We also need to set platform/ACTIVE if autodna cli expects it,
        # but starting autodna CLI via python module is safest cross-platform option
        env = os.environ.copy()
        if "AUTODNA_PLATFORM" not in env and _detect_codex_env():
            env["AUTODNA_PLATFORM"] = "CODEX"
        # Ensure worktrees resume without manual intervention during swarm runs.
        env["AUTODNA_WORKTREE_RESUME"] = "1"
        env["AUTODNA_WORKTREE_DIRTY_POLICY"] = "commit"
        env["AUTODNA_WORKTREE_SAFE_DIRECTORY"] = "1"

        repo_root = Path(__file__).resolve().parents[1]
        worktree_policy = env.get("AUTODNA_WORKTREE_DIRTY_POLICY", DIRTY_POLICY_COMMIT)
        _prepare_worker_worktrees(worktree_policy, repo_root)
        pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{repo_root}{os.pathsep}{pythonpath}" if pythonpath else str(repo_root)

        process = subprocess.Popen(
            [sys.executable, "autodna/core/engine_start.py", "--headless"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            cwd=str(repo_root),
            encoding="utf-8",
            errors="replace"
        )

        start_time = time.time()
        log_path = Path("agent/manager.log")
        log_offset = log_path.stat().st_size if log_path.exists() else 0
        output_queue = _start_output_reader(process)
        recent_output: list[str] = []

        while True:
            while True:
                try:
                    line = output_queue.get_nowait()
                except queue.Empty:
                    break
                if line is None:
                    break
                recent_output.append(line)
                if len(recent_output) > 200:
                    recent_output.pop(0)
                if "AttachConsole failed" in line:
                    logger.error("Gemini CLI console attach failed.")
                    process.terminate()
                    return "blocked", "Gemini CLI console attach failed."
                if "All fallback models exhausted. Cannot continue." in line:
                    logger.error("All configured Gemini models exhausted or unavailable.")
                    process.terminate()
                    return "blocked", "All configured Gemini models exhausted or unavailable."
                if "TerminalQuotaError" in line or "QUOTA_EXHAUSTED" in line:
                    logger.error("Gemini quota exhausted.")
                    process.terminate()
                    return "blocked", "Gemini quota exhausted."
                if "ModelNotFoundError" in line or "Requested entity was not found" in line:
                    logger.error("Gemini model not found.")
                    process.terminate()
                    return "blocked", "Gemini model not found. Update AUTODNA_MODELS or Gemini CLI config."
                if "CLI unavailable:" in line:
                    logger.error("CLI unavailable.")
                    process.terminate()
                    return "blocked", "CLI unavailable. Install the CLI or set AUTODNA_CODEX_CMD."
                if "Permission denied launching CLI" in line or "Access is denied" in line:
                    logger.error("CLI permission denied.")
                    process.terminate()
                    return "blocked", "CLI permission denied. Fix executable permissions."
                if "Failed to launch CLI:" in line:
                    logger.error("CLI failed to launch.")
                    process.terminate()
                    return "blocked", "CLI failed to launch. Verify the CLI path and permissions."

            # Check if process ended naturally
            retcode = process.poll()
            if retcode is not None:
                if retcode == 0:
                    logger.info("Swarm completed normally.")
                    return "done", None
                logger.error(f"Swarm exited with error code {retcode}")
                # Output the logs to help debug
                out, _ = process.communicate()
                if out:
                    recent_output.append(out)
                output_blob = "".join(recent_output)[-2000:]
                print(output_blob if output_blob else "No output.")
                summary = _summarize_swarm_failure("".join(recent_output))
                if summary:
                    return "blocked", summary
                return "error", None

            # Check timeout
            if time.time() - start_time > timeout_seconds:
                logger.error(f"Swarm timed out after {timeout_seconds} seconds. Terminating.")
                process.terminate()
                process.wait(timeout=5)
                return "error", "Swarm timed out."

            # Wait a bit before checking again
            time.sleep(5)

            log_offset, log_note = _scan_swarm_log(log_path, log_offset)
            if log_note:
                logger.error(log_note)
                process.terminate()
                return "blocked", log_note

            # Periodically check TASK_QUEUE.json to see if the task is done, error, etc.
            # (In headless mode the swarm might stay alive listening, depending on implementation)
            with open(TASK_QUEUE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for t in data.get("tasks", []):
                    if t.get("id") == task["id"]:
                        if t.get("status") == "done":
                            logger.info("Task marked 'done' in queue! Terminating swarm.")
                            process.terminate()
                            return "done", None
                        elif t.get("status") in ["error", "blocked"]:
                            logger.error(f"Task marked '{t.get('status')}' in queue.")
                            process.terminate()
                            return t.get("status"), t.get("notes")

    except Exception as e:
        logger.error(f"Error orchestrating swarm: {e}")
        return "error", f"Swarm orchestration error: {e}"

def commit_changes(task: Dict[str, Any]) -> None:
    """Commit changes to the current branch."""
    msg = f"feat: Auto-complete task {task['id']} - {task['title'][:50]}"

    # We purposefully exclude TASK_QUEUE and MEMORY from committing into branches
    # using the .gitignore we set up earlier. Only code changes get pushed.

    logger.info("Committing passing changes...")
    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(["git", "commit", "-m", msg], check=True)
    logger.info(f"Changes committed successfully! ({msg})")

def rollback_changes() -> None:
    """Discard uncommitted changes in the working directory."""
    logger.info("Rolling back uncommitted changes...")
    subprocess.run(["git", "restore", "."], check=True)
    subprocess.run(["git", "clean", "-fd", "--exclude=agent/traces", "--exclude=agent/reports"], check=True)
    logger.info("Rollback complete.")

def main():
    parser = argparse.ArgumentParser(description="Autonomous DNA Dogfooding Orchestrator")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without spawning swarm")
    parser.add_argument("--base-branch", default=None, help="Base branch to create self-improve branches from")
    parser.add_argument("--loop", action="store_true", help="Repeat self-improve until no tasks remain")
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=int(os.getenv("AUTODNA_SELF_IMPROVE_MAX_CYCLES", "3")),
        help="Maximum loop iterations when --loop is enabled",
    )
    args = parser.parse_args()

    logger.info("Starting Autonomous-DNA Self-Improvement Loop...")

    loop_enabled = args.loop or os.getenv("AUTODNA_SELF_IMPROVE_LOOP", "").lower() in {"1", "true", "yes"}
    max_cycles = max(1, args.max_cycles)

    dogfood_enabled = os.getenv("AUTODNA_SELF_IMPROVE_DOGFOOD", "1").lower() in {"1", "true", "yes"}
    dogfood_use_default = os.getenv("AUTODNA_SELF_IMPROVE_NO_DEFAULT_GATES", "").lower() not in {"1", "true", "yes"}
    dogfood_extra_gates = parse_gate_env(os.getenv("AUTODNA_SELF_IMPROVE_GATES", ""))
    dogfood_gates = (dogfood.DEFAULT_GATES if dogfood_use_default else []) + dogfood_extra_gates
    dogfood_out_dir = Path(os.getenv("AUTODNA_SELF_IMPROVE_DOGFOOD_DIR", "agent/dogfood_reports"))
    if dogfood_enabled:
        logger.info(f"Dogfood gating enabled. Gates: {dogfood_gates or 'NONE'}")

    always_taskgen = os.getenv("AUTODNA_SELF_IMPROVE_ALWAYS_TASKGEN", "1").lower() in {"1", "true", "yes"}
    auto_bootstrap = os.getenv("AUTODNA_SELF_IMPROVE_AUTO_BOOTSTRAP", "1").lower() in {"1", "true", "yes"}
    bootstrap_attempted = False
    dirty_policy = os.getenv("AUTODNA_SELF_IMPROVE_DIRTY_POLICY", DIRTY_POLICY_DEFAULT)
    if args.dry_run:
        proceed, stash_ref = True, None
    else:
        proceed, stash_ref = handle_dirty_working_tree(dirty_policy)
        if not proceed:
            sys.exit(0)
    cycles = 0
    try:
        while True:
            if not args.dry_run and not working_tree_is_clean():
                logger.warning("Working tree became dirty during self-improve. Aborting.")
                break

            task = select_next_task(always_taskgen)
            if not task and auto_bootstrap and not bootstrap_attempted:
                bootstrap_attempted = True
                bootstrap_queue()
                task = _select_actionable_task()
            if not task:
                cycles += 1
                if not loop_enabled or cycles >= max_cycles:
                    break
                logger.info("No tasks found after task generation. Restarting loop from the top.")
                continue

            assert task is not None # Tell type checker it's safe
            bootstrap_attempted = False

            preferred_base = args.base_branch or os.getenv("AUTODNA_SELF_IMPROVE_BASE")
            base_branch = resolve_base_branch(preferred_base)
            branch_name = f"chore/self-improve-task-{task['id']}"

            if args.dry_run:
                logger.info(f"[DRY RUN] Would check out branch: {branch_name}")
                logger.info(f"[DRY RUN] Would start swarm for task {task['id']}")
                logger.info("[DRY RUN] Would run pytest and commit if passed")
                if dogfood_enabled:
                    logger.info("[DRY RUN] Would generate dogfood baseline/after reports and evaluate gates")
                sys.exit(0)

            try:
                checkout_branch(branch_name, base_branch)

                baseline_report = None
                if dogfood_enabled:
                    try:
                        notes = f"task {task['id']}: {task['title']}"
                        baseline_report = _dogfood_report(
                            label=f"baseline-task-{task['id']}",
                            notes=notes,
                            out_dir=dogfood_out_dir,
                        )
                    except Exception as exc:
                        logger.warning(f"Dogfood baseline failed: {exc}")

                swarm_status, swarm_note = run_swarm(task)

                if swarm_status == "done":
                    tests_passed = run_tests()
                    if tests_passed:
                        dogfood_ok = True
                        dogfood_summary = None
                        if dogfood_enabled:
                            if not baseline_report:
                                dogfood_ok = False
                                dogfood_summary = "Dogfood baseline report missing."
                            else:
                                try:
                                    notes = f"task {task['id']}: {task['title']}"
                                    after_report = _dogfood_report(
                                        label=f"after-task-{task['id']}",
                                        notes=notes,
                                        out_dir=dogfood_out_dir,
                                    )
                                    dogfood_ok, dogfood_summary = _evaluate_dogfood(
                                        baseline_report,
                                        after_report,
                                        dogfood_gates,
                                    )
                                except Exception as exc:
                                    dogfood_ok = False
                                    dogfood_summary = f"Dogfood evaluation failed: {exc}"
                            if dogfood_summary:
                                if dogfood_ok:
                                    logger.info("\n" + dogfood_summary.strip())
                                else:
                                    logger.error("\n" + dogfood_summary.strip())

                        if dogfood_ok:
                            commit_changes(task)
                            update_task_status(task["id"], "done")
                            logger.info(f"Task {task['id']} completed successfully. Review branch {branch_name}.")
                        else:
                            logger.error("Dogfood gates failed. Rolling back changes.")
                            rollback_changes()
                            update_task_status(task["id"], "error", "Dogfood gates failed.")
                    else:
                        logger.error("Tests failed! Rolling back changes to prevent master corruption.")
                        rollback_changes()
                        update_task_status(task["id"], "error", "Tests failed after implementation.")
                else:
                    logger.error("Swarm failed to complete task.")
                    rollback_changes()
                    current_status, current_notes = _get_task_status(task["id"])
                    if swarm_status == "blocked":
                        if current_status != "blocked":
                            update_task_status(task["id"], "blocked", swarm_note or current_notes)
                    else:
                        update_task_status(task["id"], "error", swarm_note or current_notes or "Swarm exited with error.")

                subprocess.run(["git", "checkout", base_branch], check=True)

            except Exception as e:
                logger.exception("Catastrophic error in self-improve loop:")
                rollback_changes()
                update_task_status(task["id"], "error", f"Self-improve script crashed: {e}")
                subprocess.run(["git", "checkout", base_branch], check=True)
                break

            cycles += 1
            if not loop_enabled:
                break
            if cycles >= max_cycles:
                logger.info("Max self-improve cycles reached. Stopping.")
                break
    finally:
        if stash_ref:
            restore_stash(stash_ref)

if __name__ == "__main__":
    main()
