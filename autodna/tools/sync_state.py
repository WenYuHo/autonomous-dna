"""
tools/sync_state.py
Modern State Sync for Autonomous-DNA.
Manages TASK_QUEUE.json: reserve, complete, status.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_FILE = Path("agent/TASK_QUEUE.json")
HEARTBEAT_TTL_SECONDS = int(os.getenv("AUTODNA_TASK_HEARTBEAT_TTL", "900"))


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_db():
    if not DB_FILE.exists():
        print(f"ERROR: {DB_FILE} not found.")
        sys.exit(1)
    try:
        return json.loads(DB_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"ERROR: Failed to read {DB_FILE}: {exc}")
        sys.exit(1)


def save_db(db):
    DB_FILE.write_text(json.dumps(db, indent=2), encoding="utf-8")


def _assignee(task):
    assigned_to = task.get("assigned_to")
    if isinstance(assigned_to, str):
        assigned_to = assigned_to.strip()
    return assigned_to or None


def _parse_iso(value):
    if not value:
        return None
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


def _heartbeat_fresh(task):
    heartbeat = _parse_iso(task.get("heartbeat_at"))
    if not heartbeat:
        return False
    return datetime.now(timezone.utc) - heartbeat <= timedelta(seconds=HEARTBEAT_TTL_SECONDS)


def reserve(task_id: int, agent_id: str):
    db = load_db()
    for task in db.get("tasks", []):
        if task.get("id") != task_id:
            continue

        status = str(task.get("status", "")).lower()
        if status in {"completed", "done"}:
            print(f"ERROR: Task {task_id} is already completed.")
            sys.exit(1)

        assigned = _assignee(task)
        if status == "in_progress" and assigned and assigned != agent_id and _heartbeat_fresh(task):
            print(f"ERROR: Task {task_id} is already reserved by {assigned}.")
            sys.exit(1)

        task["status"] = "in_progress"
        task["assigned_to"] = agent_id
        task["updated_at"] = now_iso()
        task["heartbeat_at"] = now_iso()
        save_db(db)

        if status == "in_progress" and assigned and assigned != agent_id:
            print(f"[OK] Reclaimed stale Task #{task_id} from {assigned} for {agent_id}")
            return

        print(f"[OK] Reserved Task #{task_id} for {agent_id}")
        return

    print(f"ERROR: Task {task_id} not found.")
    sys.exit(1)


def mark_done(task_id: int):
    db = load_db()
    for task in db.get("tasks", []):
        if task.get("id") != task_id:
            continue
        task["status"] = "completed"
        task["updated_at"] = now_iso()
        task["heartbeat_at"] = now_iso()
        save_db(db)
        print(f"[OK] Task #{task_id} marked as COMPLETED")
        return
    print(f"ERROR: Task {task_id} not found.")
    sys.exit(1)


def status():
    db = load_db()
    tasks = db.get("tasks", [])
    in_progress = []
    stale_claimable = []
    available = []
    for task in tasks:
        status_value = str(task.get("status", "")).lower()
        if status_value == "in_progress":
            if _heartbeat_fresh(task):
                in_progress.append(task)
            else:
                stale_claimable.append(task)
                available.append(task)
        elif status_value == "pending":
            available.append(task)
    completed = [task for task in tasks if str(task.get("status", "")).lower() in {"completed", "done"}]

    print(f"\nIN PROGRESS: {len(in_progress)}")
    for task in in_progress:
        assigned = _assignee(task) or "UNASSIGNED"
        print(f"  [{task['id']}] {task['title']} (Assigned: {assigned})")

    print(f"\nSTALE CLAIMABLE: {len(stale_claimable)}")
    for task in stale_claimable:
        assigned = _assignee(task) or "UNASSIGNED"
        print(f"  [{task['id']}] {task['title']} (Last assigned: {assigned})")

    print(f"\nAVAILABLE: {len(available)}")
    for task in available[:5]:
        label = " [STALE]" if str(task.get("status", "")).lower() == "in_progress" else ""
        print(f"  [{task['id']}] {task['title']}{label}")

    print(f"\nCOMPLETED: {len(completed)}")


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: python tools/sync_state.py [TASK_ID --reserve AGENT_ID | --done | --status]")
        sys.exit(0)

    if args[0] == "--status":
        status()
        return

    try:
        task_id = int(args[0])
    except ValueError:
        print(f"ERROR: Task ID must be an integer, got '{args[0]}'")
        sys.exit(1)

    if len(args) < 2:
        sys.exit(1)

    if args[1] == "--reserve" and len(args) >= 3:
        reserve(task_id, args[2])
    elif args[1] == "--done":
        mark_done(task_id)
    else:
        print(f"Unknown command/args: {args}")


if __name__ == "__main__":
    main()
