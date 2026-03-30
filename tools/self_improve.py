"""
tools/self_improve.py
Single-agent orchestrator for the Autonomous-DNA self-improvement loop.
"""

import argparse
import hashlib
import json
import logging
import os
import queue
import shlex
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
from autodna.tools import outcomes as outcome_api
from autodna.tools import recurring_issues as issue_detector
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
_KEEP_ASSIGNEE = object()
DEFAULT_RESEARCH_TOPICS = [
    "latest state of the art AI coding agent system prompts and framework architecture 2026",
    "ai coding agent eval harnesses, regression gates, and benchmark suites 2025 2026",
    "tool-use reliability, prompt injection defenses, and guardrails for coding agents",
]
LEFTOVER_TASK_TITLE = "[FOLLOWUP] Triage leftover workspace files"
LEFTOVER_SIGNATURE_KEY = "leftover_signature="
RESEARCH_POLICIES = {"bootstrap", "bootstrap-only", "stale", "always", "never"}
DONE_STATUSES = {"done", "completed"}
DOGFOOD_OUT_DIR = Path("agent/dogfood_reports")
RECEIPT_PREFIX = "AUTODNA_RECEIPT "


def parse_gate_env(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or not str(value).strip():
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_command(command: str) -> list[str]:
    text = (command or "").strip()
    if not text:
        return []
    return shlex.split(text, posix=os.name != "nt")


def _format_command(command: list[str]) -> str:
    return " ".join(command)


def _merge_notes(*parts: Any) -> Optional[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if part is None:
            continue
        text = str(part).strip()
        if not text or text in seen:
            continue
        merged.append(text)
        seen.add(text)
    return "\n\n".join(merged) if merged else None


def _receipt_line(kind: str, **payload: Any) -> str:
    return f"{RECEIPT_PREFIX}{json.dumps({'kind': kind, **payload}, sort_keys=True)}"


def _parse_receipts(text: Optional[str]) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for line in (text or "").splitlines():
        if not line.startswith(RECEIPT_PREFIX):
            continue
        payload = line[len(RECEIPT_PREFIX) :].strip()
        if not payload:
            continue
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            receipts.append(parsed)
    return receipts


def _has_success_receipt(text: Optional[str], kind: str) -> bool:
    for receipt in _parse_receipts(text):
        if receipt.get("kind") == kind and receipt.get("status") == "pass":
            return True
    return False


def _has_required_done_receipts(text: Optional[str]) -> bool:
    return _has_success_receipt(text, "tests") and _has_success_receipt(text, "evaluation")


def _strip_receipts(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    cleaned = "\n".join(line for line in str(text).splitlines() if not line.startswith(RECEIPT_PREFIX)).strip()
    return cleaned or None


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


def _extract_porcelain_path(line: str) -> str:
    text = (line or "").rstrip()
    if not text:
        return ""
    payload = text[3:] if len(text) > 3 else text
    payload = payload.strip()
    if " -> " in payload:
        payload = payload.split(" -> ", 1)[1].strip()
    return payload


def _collect_leftover_files() -> list[str]:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []

    files = []
    for raw_line in (result.stdout or "").splitlines():
        path = _extract_porcelain_path(raw_line)
        if path:
            files.append(path)
    return sorted(set(files))


def _leftover_signature(files: list[str]) -> str:
    normalized = "\n".join(sorted(set(files)))
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()
    return digest[:12]


def _find_open_leftover_followup(signature: str, tasks: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    marker = f"{LEFTOVER_SIGNATURE_KEY}{signature}"
    for task in tasks:
        status = str(task.get("status", "")).lower()
        if status in {"done", "completed", "info"}:
            continue
        title = str(task.get("title", "")).strip()
        description = str(task.get("description", "")).strip()
        if title == LEFTOVER_TASK_TITLE and marker in description:
            return task
    return None


def _create_leftover_followup_task(files: list[str], signature: str) -> None:
    preview = ", ".join(files[:5])
    if len(files) > 5:
        preview = f"{preview}, +{len(files) - 5} more"
    description = (
        "No actionable queue task was found, but leftover workspace files remain. "
        "Resolve files that match the active request now, and queue unrelated work as concrete tasks. "
        f"{LEFTOVER_SIGNATURE_KEY}{signature}; files={preview}"
    )
    ref = files[0] if files else "NONE"
    task_api.add_task(LEFTOVER_TASK_TITLE, description, ref=ref)


def _ensure_leftover_followup_task() -> dict[str, Any]:
    files = _collect_leftover_files()
    if not files:
        return {"created": False, "task_id": None, "file_count": 0}

    signature = _leftover_signature(files)
    existing = _find_open_leftover_followup(signature, _load_tasks())
    if existing:
        return {"created": False, "task_id": existing.get("id"), "file_count": len(files)}

    _create_leftover_followup_task(files, signature)
    created = _find_open_leftover_followup(signature, _load_tasks())
    return {"created": True, "task_id": created.get("id") if created else None, "file_count": len(files)}


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


def _normalize_research_policy(value: Optional[str]) -> str:
    policy = (value or "").strip().lower()
    if not policy:
        return "stale"
    if policy == "bootstrap":
        return "bootstrap-only"
    if policy in RESEARCH_POLICIES:
        return policy
    logger.warning("Unknown research refresh policy %r. Falling back to stale.", value)
    return "stale"


def _research_artifact_dir() -> Path:
    return Path(os.getenv("AUTODNA_SELF_IMPROVE_RESEARCH_DIR", "agent/skills/auto_generated"))


def _latest_research_artifact_time() -> Optional[datetime]:
    artifact_dir = _research_artifact_dir()
    if not artifact_dir.exists():
        return None

    latest: Optional[datetime] = None
    for artifact in artifact_dir.rglob("*.md"):
        if not artifact.is_file():
            continue
        modified = datetime.fromtimestamp(artifact.stat().st_mtime, timezone.utc)
        if latest is None or modified > latest:
            latest = modified
    return latest


def _should_refresh_research(force: bool = False, queue_empty: bool = False) -> bool:
    if force:
        return True

    policy = _normalize_research_policy(os.getenv("AUTODNA_SELF_IMPROVE_RESEARCH_POLICY", "stale"))
    if policy == "never":
        return False
    if policy == "always":
        return True
    if policy == "bootstrap-only":
        return queue_empty

    max_age_seconds = max(0, int(os.getenv("AUTODNA_SELF_IMPROVE_RESEARCH_MAX_AGE_SECONDS", "86400")))
    latest = _latest_research_artifact_time()
    if latest is None:
        return True
    return datetime.now(timezone.utc) - latest >= timedelta(seconds=max_age_seconds)


def _refresh_research(topic: Optional[str] = None) -> bool:
    resolved_topic = topic or _pick_research_topic()
    logger.info("Refreshing research artifacts for topic: %s", resolved_topic)
    return _run_cli_step(
        [sys.executable, "autodna/cli.py", "research", "--timestamped", resolved_topic],
        "Auto-research",
        RESEARCH_TIMEOUT_SECONDS,
    )


def _maybe_refresh_research(force: bool = False, queue_empty: bool = False) -> bool:
    if not _should_refresh_research(force=force, queue_empty=queue_empty):
        return False
    return _refresh_research()


def _capture_dogfood_report(label: str, notes: str = "") -> Path:
    timestamp = _now_iso()
    benchmark = None
    if _bool_env("AUTODNA_SELF_IMPROVE_DOGFOOD_INCLUDE_BENCHMARK", False):
        benchmark = dogfood.scan_text_tree(Path(".").resolve())
    report = dogfood.build_report(
        label=label,
        timestamp=timestamp,
        repo_root=Path(".").resolve(),
        notes=notes,
        memory_facts=dogfood.count_memory_facts(Path("agent/MEMORY.md")),
        task_snapshot=task_snapshot_from_json(TASK_QUEUE_FILE),
        benchmark=benchmark,
    )
    return dogfood.write_report(report, DOGFOOD_OUT_DIR, label, timestamp)


def _bootstrap_queue(research_already_refreshed: bool = False, force_research: bool = False) -> None:
    refreshed = research_already_refreshed
    if not refreshed and _should_refresh_research(force=force_research, queue_empty=True):
        refreshed = _refresh_research()
    if refreshed:
        logger.info("No actionable tasks. Bootstrapping task generation after research refresh.")
    else:
        logger.info("No actionable tasks. Bootstrapping task generation without research refresh.")
    _run_cli_step([sys.executable, "autodna/cli.py", "taskgen", "--if-empty"], "Auto-taskgen", TASKGEN_TIMEOUT_SECONDS)
    try:
        report_path = _capture_dogfood_report("bootstrap", notes="empty-queue bootstrap snapshot")
        logger.info("Bootstrap dogfood snapshot written to %s", report_path)
    except Exception as exc:
        logger.warning("Bootstrap dogfood snapshot failed: %s", exc)


def _resolve_test_command() -> list[str]:
    env_command = (
        os.getenv("AUTODNA_SELF_IMPROVE_TEST_CMD", "").strip()
        or os.getenv("AUTODNA_GIT_TEST_CMD", "").strip()
    )
    command = _parse_command(env_command) if env_command else []
    return command or [sys.executable, "-m", "pytest", "-q"]


def _run_required_tests() -> dict[str, Any]:
    command = _resolve_test_command()
    timeout_seconds = max(1, int(os.getenv("AUTODNA_SELF_IMPROVE_TEST_TIMEOUT", "1200")))
    receipt: dict[str, Any] = {
        "kind": "tests",
        "status": "fail",
        "command": _format_command(command),
    }
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
        receipt["reason"] = f"timed out after {timeout_seconds}s"
        return receipt
    except Exception as exc:
        receipt["reason"] = str(exc)
        return receipt

    receipt["exit_code"] = result.returncode
    output_tail = "\n".join(part for part in ((result.stdout or "").strip(), (result.stderr or "").strip()) if part)
    if output_tail:
        receipt["output_tail"] = output_tail[-600:]
    if result.returncode == 0:
        receipt["status"] = "pass"
    return receipt


def _task_status_for_id(task_id: int) -> tuple[str, dict[str, Any]]:
    current_task = next((item for item in _load_tasks() if item.get("id") == task_id), {})
    return str(current_task.get("status", "")).lower(), current_task


def _resolve_dogfood_gates() -> list[str]:
    extra_gates = parse_gate_env(os.getenv("AUTODNA_SELF_IMPROVE_GATES", ""))
    if _bool_env("AUTODNA_SELF_IMPROVE_NO_DEFAULT_GATES", False):
        return extra_gates
    return dogfood.DEFAULT_GATES + extra_gates


def _run_evaluation_gate(task_id: int, baseline_report: Optional[Path], notes: str = "") -> dict[str, Any]:
    gates = _resolve_dogfood_gates()
    receipt: dict[str, Any] = {
        "kind": "evaluation",
        "status": "fail",
        "gates": gates,
    }
    if baseline_report is None:
        receipt["reason"] = "missing baseline report"
        return receipt

    try:
        after_report = _capture_dogfood_report(f"task-{task_id}-after", notes=notes or f"post-task {task_id}")
        baseline = dogfood.parse_report(baseline_report)
        after = dogfood.parse_report(after_report)
        deltas = dogfood.compare_reports(baseline, after)
        failures = dogfood.evaluate_gates(after, deltas, gates)
        summary = dogfood.format_compare_summary(
            baseline_report,
            after_report,
            baseline,
            after,
            deltas,
            gates,
            failures,
        )
        compare_report = dogfood.write_report(summary, DOGFOOD_OUT_DIR, f"compare-task-{task_id}", _now_iso())
    except Exception as exc:
        receipt["reason"] = str(exc)
        return receipt

    receipt.update(
        {
            "baseline_report": str(baseline_report),
            "after_report": str(after_report),
            "compare_report": str(compare_report),
            "deltas": deltas,
            "failures": failures,
        }
    )
    if not failures:
        receipt["status"] = "pass"
    return receipt


def _finalize_done_status(task_id: int, baseline_report: Optional[Path], run_note: Optional[str]) -> tuple[str, Optional[str]]:
    current_task = next((item for item in _load_tasks() if item.get("id") == task_id), {})
    current_status = str(current_task.get("status", "")).lower()
    current_notes = _strip_receipts(current_task.get("notes"))
    base_notes = _merge_notes(run_note, current_notes)
    if current_status not in DONE_STATUSES:
        return "error", _merge_notes(
            base_notes,
            "Self-improve controller rejected done: task was not marked completed in TASK_QUEUE.",
        )

    test_receipt = _run_required_tests()
    eval_receipt = _run_evaluation_gate(task_id, baseline_report, notes=base_notes or "")
    notes_with_receipts = _merge_notes(
        base_notes,
        _receipt_line("tests", **{key: value for key, value in test_receipt.items() if key != "kind"}),
        _receipt_line("evaluation", **{key: value for key, value in eval_receipt.items() if key != "kind"}),
    )

    if test_receipt.get("status") == "pass" and eval_receipt.get("status") == "pass":
        return "done", notes_with_receipts

    failures: list[str] = []
    if test_receipt.get("status") != "pass":
        failures.append("required tests failed")
    if eval_receipt.get("status") != "pass":
        failures.append("dogfood evaluation gate failed")
    if not failures:
        failures.append("missing completion receipts")
    return "error", _merge_notes(
        notes_with_receipts,
        f"Self-improve controller rejected done: {', '.join(failures)}.",
    )


def _git_preflight(fetch: bool = True) -> tuple[bool, Optional[str]]:
    state = git_ops.inspect_git_state(fetch=fetch, allow_dirty=git_ops.is_lab_mode())
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
            current_status, current_task = _task_status_for_id(task["id"])
            if current_status in {"done", "completed"}:
                return "done", None
            if current_status in {"error", "blocked"}:
                return current_status, current_task.get("notes")
            if process.returncode == 0:
                return "error", "Agent exited cleanly without marking the task completed."
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
        help="Force research/taskgen bootstrap before selecting a task",
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
    logger.info("Dogfood gates configured: %s", _resolve_dogfood_gates())
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

    research_refreshed = _maybe_refresh_research(force=args.bootstrap, queue_empty=False)
    if args.bootstrap:
        _bootstrap_queue(research_already_refreshed=research_refreshed, force_research=True)

    task = _select_actionable_task(args.agent_name)
    if not task and os.getenv("AUTODNA_SELF_IMPROVE_AUTO_BOOTSTRAP", "1").lower() in {"1", "true", "yes"}:
        _bootstrap_queue(research_already_refreshed=research_refreshed, force_research=False)
        task = _select_actionable_task(args.agent_name)

    if not task:
        leftover_followup = _ensure_leftover_followup_task()
        if leftover_followup.get("created"):
            logger.info(
                "Created leftover follow-up task %s for %s workspace file(s).",
                leftover_followup.get("task_id"),
                leftover_followup.get("file_count"),
            )
            task = _select_actionable_task(args.agent_name)
        elif leftover_followup.get("task_id"):
            logger.info(
                "Leftover follow-up task %s already exists for %s workspace file(s).",
                leftover_followup.get("task_id"),
                leftover_followup.get("file_count"),
            )
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
    baseline_report: Optional[Path] = None
    try:
        baseline_report = _capture_dogfood_report(f"task-{task['id']}-baseline", notes=f"pre-task {task['id']} baseline")
    except Exception as exc:
        logger.warning("Baseline dogfood snapshot failed for task %s: %s", task["id"], exc)
    run_status, run_note = run_agent(task, timeout_seconds=args.timeout, agent_name=args.agent_name)

    final_status = run_status
    final_note = run_note
    if run_status in DONE_STATUSES:
        final_status, final_note = _finalize_done_status(task["id"], baseline_report, run_note)
        if final_status == "done":
            _update_task_state(task["id"], "completed", final_note, assigned_to=None)
        else:
            _update_task_state(task["id"], "error", final_note, assigned_to=None)
    else:
        current_task = next((item for item in _load_tasks() if item.get("id") == task["id"]), {})
        current_status = str(current_task.get("status", "")).lower()
        if current_status not in {"error", "blocked", "done", "completed"}:
            _update_task_state(task["id"], run_status, run_note, assigned_to=None)
        final_status = run_status
        final_note = run_note

    outcomes_dir = Path("agent/run_outcomes")
    outcome_api.record_outcome(task["id"], final_status, final_note or "", args.agent_name, outcomes_dir)

    if final_status == "done":
        logger.info("Self-improve task %s completed.", task["id"])
        return

    # For errors or blocks, scan for recurring issues
    try:
        issues_db = Path("agent/issues.db")
        recurring = issue_detector.detect_recurring_issues(outcomes_dir, issues_db)
        if recurring:
            logger.warning("Detected %d recurring issue(s). Auto-creating fix tasks.", len(recurring))
            issue_detector.auto_create_fix_tasks(recurring, TASK_QUEUE_FILE)
    except Exception as exc:
        logger.warning("Recurring issue detection failed: %s", exc)

    if final_note:
        logger.error("Self-improve task %s ended as %s: %s", task["id"], final_status, final_note)
    else:
        logger.error("Self-improve task %s ended as %s.", task["id"], final_status)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
