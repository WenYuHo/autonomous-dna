"""
tools/self_improve.py
Single-agent orchestrator for the Autonomous-DNA self-improvement loop.
"""

import argparse
import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from autodna.core import engine_start
from autodna.tools import dogfood
from autodna.tools import tasks as task_api
from tools import git_ops

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

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
UNBLOCKED_STATUSES = {"done", "info", "completed"}
HEARTBEAT_TTL_SECONDS = int(os.getenv("AUTODNA_TASK_HEARTBEAT_TTL", "900"))
RESEARCH_TIMEOUT_SECONDS = 300
TASKGEN_TIMEOUT_SECONDS = 120
EVAL_TIMEOUT_SECONDS = 120
_KEEP_ASSIGNEE = object()
DEFAULT_RESEARCH_TOPICS = [
    "latest state of the art AI coding agent system prompts and framework architecture 2026",
    "ai coding agent eval harnesses, regression gates, and benchmark suites 2025 2026",
    "tool-use reliability, prompt injection defenses, and guardrails for coding agents",
]


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


def _load_queue_data() -> dict[str, Any]:
    if not TASK_QUEUE_FILE.exists():
        return {"tasks": []}
    data = json.loads(TASK_QUEUE_FILE.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {"tasks": []}


def _save_queue_data(data: dict[str, Any]) -> None:
    TASK_QUEUE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_tasks() -> list[dict[str, Any]]:
    tasks = _load_queue_data().get("tasks", [])
    return tasks if isinstance(tasks, list) else []


def _task_by_id(tasks: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {task.get("id"): task for task in tasks if isinstance(task.get("id"), int)}


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


def _normalize_assignee(value: Any) -> Optional[str]:
    if isinstance(value, str):
        value = value.strip()
    return value or None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _heartbeat_fresh(task: dict[str, Any], ttl_seconds: int = HEARTBEAT_TTL_SECONDS) -> bool:
    heartbeat = _parse_iso(task.get("heartbeat_at"))
    if not heartbeat:
        return False
    return datetime.now(timezone.utc) - heartbeat <= timedelta(seconds=ttl_seconds)


def _is_blocked(task: dict[str, Any], by_id: dict[int, dict[str, Any]]) -> bool:
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


def _active_agents(tasks: list[dict[str, Any]]) -> set[str]:
    active = set()
    for task in tasks:
        if str(task.get("status", "")).lower() != "in_progress":
            continue
        if not _heartbeat_fresh(task):
            continue
        assigned = _normalize_assignee(task.get("assigned_to"))
        if assigned:
            active.add(assigned)
    return active


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
        logger.warning("%s timed out after %ss.", label, timeout_seconds)
        return False
    except Exception as exc:
        logger.warning("%s failed to launch: %s", label, exc)
        return False
    if result.returncode != 0:
        logger.warning("%s failed (exit code %s).", label, result.returncode)
        if result.stdout:
            logger.warning(result.stdout.strip()[-1000:])
        if result.stderr:
            logger.warning(result.stderr.strip()[-1000:])
        return False
    return True


def _select_actionable_task(agent_name: str) -> Optional[dict[str, Any]]:
    tasks = _load_tasks()
    by_id = _task_by_id(tasks)

    for task in tasks:
        title = task.get("title", "").strip().upper()
        if title.startswith("CYCLE"):
            continue
        status = str(task.get("status", "")).lower()
        assigned = _normalize_assignee(task.get("assigned_to"))
        if status != "in_progress":
            continue
        if _is_blocked(task, by_id):
            continue
        if assigned == agent_name or assigned is None or not _heartbeat_fresh(task):
            return task

    for task in tasks:
        if str(task.get("status", "")).lower() != "pending":
            continue
        if task.get("title", "").strip().upper().startswith("CYCLE"):
            continue
        if _is_blocked(task, by_id):
            continue
        return task

    for task in tasks:
        if str(task.get("status", "")).lower() not in {"error", "blocked"}:
            continue
        if task.get("title", "").strip().upper().startswith("CYCLE"):
            continue
        if _is_blocked(task, by_id):
            continue
        return task

    return None


def _claim_task_for_agent(task_id: int, agent_name: str) -> bool:
    data = _load_queue_data()
    tasks = data.get("tasks", [])
    now = _now_iso()

    for task in tasks:
        if task.get("id") != task_id:
            continue

        status = str(task.get("status", "")).lower()
        assigned = _normalize_assignee(task.get("assigned_to"))

        if status in {"done", "completed"}:
            return False

        if status == "in_progress":
            if assigned and assigned != agent_name and _heartbeat_fresh(task):
                return False
            task["assigned_to"] = agent_name
            task["updated_at"] = now
            task["heartbeat_at"] = now
            _save_queue_data(data)
            return True

        task["status"] = "in_progress"
        task["assigned_to"] = agent_name
        task["updated_at"] = now
        task["heartbeat_at"] = now
        _save_queue_data(data)
        return True

    return False


def _update_task_state(
    task_id: int,
    status: str,
    notes: Optional[str] = None,
    assigned_to: Any = _KEEP_ASSIGNEE,
) -> None:
    data = _load_queue_data()
    tasks = data.get("tasks", [])
    now = _now_iso()
    for task in tasks:
        if task.get("id") != task_id:
            continue
        task["status"] = status
        task["updated_at"] = now
        task["heartbeat_at"] = now
        if notes is not None:
            task["notes"] = notes
        if assigned_to is not _KEEP_ASSIGNEE:
            task["assigned_to"] = assigned_to
        _save_queue_data(data)
        return


def _pick_research_topic() -> str:
    env_topic = os.getenv("AUTODNA_SELF_IMPROVE_RESEARCH_TOPIC", "").strip()
    if env_topic:
        return env_topic
    day_index = int(time.time() // 86400) % len(DEFAULT_RESEARCH_TOPICS)
    return DEFAULT_RESEARCH_TOPICS[day_index]


def _bootstrap_queue() -> None:
    topic = _pick_research_topic()
    logger.info("No actionable tasks. Bootstrapping research/taskgen/eval for topic: %s", topic)
    _run_cli_step([sys.executable, "autodna/cli.py", "research", "--timestamped", topic], "Auto-research", RESEARCH_TIMEOUT_SECONDS)
    _run_cli_step([sys.executable, "autodna/cli.py", "taskgen", "--if-empty"], "Auto-taskgen", TASKGEN_TIMEOUT_SECONDS)
    _run_cli_step([sys.executable, "autodna/cli.py", "eval"], "Auto-eval", EVAL_TIMEOUT_SECONDS)


def _git_preflight(fetch: bool = True) -> tuple[bool, Optional[str]]:
    state = git_ops.inspect_git_state(fetch=fetch)
    if state.get("ok"):
        return True, None
    issues = state.get("issues", [])
    if not issues:
        return False, "Git preflight failed."
    return False, " ".join(issues)


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


def run_agent(task: dict[str, Any], timeout_seconds: int, agent_name: str) -> tuple[str, Optional[str]]:
    logger.info("Launching single-agent runner for task %s.", task["id"])
    env = os.environ.copy()
    if os.environ.get("CODEX_SHELL") == "1":
        env.setdefault("AUTODNA_PLATFORM", "CODEX")

    mission = engine_start.build_agent_mission(agent_name, task["id"])
    process = subprocess.Popen(
        [sys.executable, "-m", "autodna.core.agent_runner", agent_name, mission],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    output_queue = _start_output_reader(process)
    recent_output: list[str] = []
    start_time = time.time()

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
            if "All fallback models exhausted. Cannot continue." in line:
                process.terminate()
                return "blocked", "All configured models exhausted or unavailable."
            if "CLI unavailable:" in line:
                process.terminate()
                return "blocked", "CLI unavailable. Install the configured agent CLI."
            if "Permission denied launching CLI" in line or "Access is denied" in line:
                process.terminate()
                return "blocked", "CLI permission denied."

        if process.poll() is not None:
            if process.returncode == 0:
                return "done", None
            return "error", "".join(recent_output)[-2000:] or None

        if time.time() - start_time > timeout_seconds:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            return "error", "Single-agent run timed out."

        for current_task in _load_tasks():
            if current_task.get("id") != task["id"]:
                continue
            status = str(current_task.get("status", "")).lower()
            if status in {"done", "completed"}:
                process.terminate()
                return "done", None
            if status in {"error", "blocked"}:
                process.terminate()
                return status, current_task.get("notes")
        time.sleep(5)


def _handle_legacy_actions(argv: list[str]) -> bool:
    if not argv or argv[0] not in {"next", "mark-done", "mark-error"}:
        return False
    parser = argparse.ArgumentParser(description="Autonomous DNA Self-Improvement Bridge")
    parser.add_argument("action", choices=["next", "mark-done", "mark-error"])
    parser.add_argument("--id", type=int, help="Task ID")
    parser.add_argument("--notes", help="Optional completion/error notes")
    args = parser.parse_args(argv)

    if args.action == "next":
        task = task_api.get_next_task()
        print(json.dumps(task) if task else "null")
    elif args.action == "mark-done":
        if not args.id:
            print("ERROR: --id required for mark-done")
            sys.exit(1)
        task_api.complete_task(args.id, args.notes)
    elif args.action == "mark-error":
        if not args.id:
            print("ERROR: --id required for mark-error")
            sys.exit(1)
        task_api.fail_task(args.id, args.notes)
    return True


def main():
    argv = sys.argv[1:]
    if _handle_legacy_actions(argv):
        return

    parser = argparse.ArgumentParser(description="Autonomous DNA Self-Improvement Orchestrator")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without launching the agent")
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.getenv("AUTODNA_SELF_IMPROVE_TIMEOUT", "1800")),
        help="Maximum seconds to wait for one task run",
    )
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Force research/taskgen/eval bootstrap before selecting a task",
    )
    parser.add_argument(
        "--agent-name",
        default=os.getenv("AUTODNA_SELF_IMPROVE_AGENT", os.getenv("AUTODNA_AGENT_NAME", "autodna")),
        help="Agent label to use when claiming tasks",
    )
    parser.add_argument("--skip-git-preflight", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-git-fetch", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    logger.info("Starting Autonomous-DNA Self-Improvement Loop...")
    logger.info("Dogfood gates configured: %s", dogfood.DEFAULT_GATES + parse_gate_env(os.getenv("AUTODNA_SELF_IMPROVE_GATES", "")))
    logger.info("Active assigned agents with fresh heartbeats: %s", sorted(_active_agents(_load_tasks())) or "none")
    logger.info("Queue snapshot: %s", task_snapshot_from_json(TASK_QUEUE_FILE))

    skip_git_preflight = args.skip_git_preflight or os.getenv("AUTODNA_SELF_IMPROVE_SKIP_GIT_PREFLIGHT", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if not skip_git_preflight:
        git_ok, git_note = _git_preflight(fetch=not args.no_git_fetch)
        if not git_ok:
            logger.error("Git preflight blocked self-improve: %s", git_note)
            raise SystemExit(1)

    if args.bootstrap:
        _bootstrap_queue()

    task = _select_actionable_task(args.agent_name)
    if not task and os.getenv("AUTODNA_SELF_IMPROVE_AUTO_BOOTSTRAP", "1").lower() in {"1", "true", "yes"}:
        _bootstrap_queue()
        task = _select_actionable_task(args.agent_name)

    if not task:
        logger.info("No actionable self-improvement task found.")
        return

    if args.dry_run:
        logger.info("[DRY RUN] Would run task %s - %s as %s", task["id"], task["title"], args.agent_name)
        return

    if not _claim_task_for_agent(task["id"], args.agent_name):
        logger.error("Failed to claim task %s for %s.", task["id"], args.agent_name)
        raise SystemExit(1)

    task = next((item for item in _load_tasks() if item.get("id") == task["id"]), task)
    run_status, run_note = run_agent(task, timeout_seconds=args.timeout, agent_name=args.agent_name)
    if run_status == "done":
        logger.info("Self-improve task %s completed.", task["id"])
        return

    current_task = next((item for item in _load_tasks() if item.get("id") == task["id"]), {})
    current_status = str(current_task.get("status", "")).lower()
    if current_status not in {"error", "blocked", "done", "completed"}:
        _update_task_state(task["id"], run_status, run_note, assigned_to=None)

    if run_note:
        logger.error("Self-improve task %s ended as %s: %s", task["id"], run_status, run_note)
    else:
        logger.error("Self-improve task %s ended as %s.", task["id"], run_status)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
