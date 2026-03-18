"""
tools/self_improve.py
Refactored Linear Task Manager for Autonomous-DNA.
Identifies the next task for the primary agent to execute.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Setup basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TASK_QUEUE_FILE = Path("agent/TASK_QUEUE.json")
UNBLOCKED_STATUSES = {"done", "info", "completed"}

def _load_tasks():
    if not TASK_QUEUE_FILE.exists():
        return []
    try:
        data = json.loads(TASK_QUEUE_FILE.read_text(encoding="utf-8"))
        return data.get("tasks", [])
    except Exception:
        return []

def _task_by_id(tasks):
    return {t.get("id"): t for t in tasks if isinstance(t.get("id"), int)}

def _is_blocked(task, by_id):
    blocked_by = task.get("blocked_by")
    if blocked_by is None: return False
    blocker = by_id.get(blocked_by)
    if not blocker: return False
    status = str(blocker.get("status", "")).lower()
    return status not in UNBLOCKED_STATUSES

def get_next_task():
    """Returns the next actionable task (pending or retryable error)."""
    tasks = _load_tasks()
    by_id = _task_by_id(tasks)

    # 1. Look for pending
    for task in tasks:
        if task.get("status") == "pending" and not _is_blocked(task, by_id):
            if not task.get("title", "").strip().upper().startswith("CYCLE"):
                return task

    # 2. Look for error/blocked to retry
    for task in tasks:
        if task.get("status") in {"error", "blocked"} and not _is_blocked(task, by_id):
            if not task.get("title", "").strip().upper().startswith("CYCLE"):
                return task
    
    return None

def update_task_status(task_id, status, notes=None):
    if not TASK_QUEUE_FILE.exists(): return
    try:
        data = json.loads(TASK_QUEUE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return
    for task in data.get("tasks", []):
        if task.get("id") == task_id:
            task["status"] = status
            if notes: task["notes"] = notes
            task["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            break
    TASK_QUEUE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["next", "mark-done", "mark-error"])
    parser.add_argument("--id", type=int)
    parser.add_argument("--notes")
    args = parser.parse_args()

    if args.action == "next":
        task = get_next_task()
        if task:
            print(json.dumps(task))
        else:
            print("null")
    elif args.action == "mark-done" and args.id:
        update_task_status(args.id, "done", args.notes)
        print(f"Task {args.id} marked done.")
    elif args.action == "mark-error" and args.id:
        update_task_status(args.id, "error", args.notes)
        print(f"Task {args.id} marked error.")

if __name__ == "__main__":
    main()
