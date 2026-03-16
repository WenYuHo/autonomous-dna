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
import re
import queue
import threading
from pathlib import Path

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

from typing import Any, Dict, Optional

def require_clean_working_tree() -> bool:
    """Ensure no uncommitted changes before starting."""
    result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.stdout.strip():
        logger.warning("Working tree is not clean. Skipping self-improve.")
        print(result.stdout)
        return False
    return True

def _load_tasks() -> list[Dict[str, Any]]:
    if not TASK_QUEUE_FILE.exists():
        logger.info(f"{TASK_QUEUE_FILE} not found. No pending tasks to run.")
        return []
    with open(TASK_QUEUE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("tasks", [])


def _task_by_id(tasks: list[Dict[str, Any]]) -> dict[int, Dict[str, Any]]:
    return {t.get("id"): t for t in tasks if isinstance(t.get("id"), int)}


def _is_blocked(task: Dict[str, Any], by_id: dict[int, Dict[str, Any]]) -> bool:
    blocked_by = task.get("blocked_by")
    if blocked_by is None:
        return False
    blocker = by_id.get(blocked_by)
    if not blocker:
        return False
    return blocker.get("status") not in ("done", "info")


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


def select_next_task(always_taskgen: bool) -> Optional[Dict[str, Any]]:
    if always_taskgen:
        _run_taskgen_if_available()

    task = get_next_task()
    if task:
        return task

    retry_task = get_retry_task()
    if retry_task:
        update_task_status(retry_task["id"], "pending", "Auto-retry after error.")
        return retry_task

    if not always_taskgen:
        logger.info("No actionable tasks found. Attempting task generation.")
        if _run_taskgen_if_available():
            return get_next_task()

    return None


def _run_taskgen_if_available() -> bool:
    command = [sys.executable, "autodna/cli.py", "taskgen", "--if-empty"]
    try:
        result = subprocess.run(command, capture_output=True, text=True)
    except Exception as exc:
        logger.warning(f"Task generation failed to launch: {exc}")
        return False
    if result.returncode != 0:
        logger.warning("Task generation failed.")
        if result.stdout:
            logger.warning(result.stdout.strip()[-1000:])
        if result.stderr:
            logger.warning(result.stderr.strip()[-1000:])
        return False
    return True

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

        process = subprocess.Popen(
            ["python", "-m", "autodna.cli", "start", "--headless"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
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

    always_taskgen = os.getenv("AUTODNA_SELF_IMPROVE_ALWAYS_TASKGEN", "1").lower() in {"1", "true", "yes"}
    cycles = 0
    while True:
        if not args.dry_run:
            if not require_clean_working_tree():
                sys.exit(0)

        task = select_next_task(always_taskgen)
        if not task:
            cycles += 1
            if not loop_enabled or cycles >= max_cycles:
                break
            logger.info("No tasks found after task generation. Restarting loop from the top.")
            continue

        assert task is not None # Tell type checker it's safe

        preferred_base = args.base_branch or os.getenv("AUTODNA_SELF_IMPROVE_BASE")
        base_branch = resolve_base_branch(preferred_base)
        branch_name = f"chore/self-improve-task-{task['id']}"

        if args.dry_run:
            logger.info(f"[DRY RUN] Would check out branch: {branch_name}")
            logger.info(f"[DRY RUN] Would start swarm for task {task['id']}")
            logger.info("[DRY RUN] Would run pytest and commit if passed")
            sys.exit(0)

        try:
            checkout_branch(branch_name, base_branch)

            swarm_status, swarm_note = run_swarm(task)

            if swarm_status == "done":
                tests_passed = run_tests()
                if tests_passed:
                    commit_changes(task)
                    update_task_status(task["id"], "done")
                    logger.info(f"Task {task['id']} completed successfully. Review branch {branch_name}.")
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

if __name__ == "__main__":
    main()
