"""
scripts/sync_state.py (Ralph Extension)
Modern State Sync for Autonomous-DNA.
Manages TASK_QUEUE.json: reserve, complete, status.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_FILE = Path("agent/TASK_QUEUE.json")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


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


def reserve(task_id: int, agent_id: str):
    db = load_db()
    for task in db.get("tasks", []):
        if task.get("id") != task_id:
            continue
        if str(task.get("status", "")).lower() in {"completed", "done"}:
            print(f"ERROR: Task {task_id} is already completed.")
            sys.exit(1)
        assigned = _assignee(task)
        if assigned and assigned != agent_id:
            print(f"ERROR: Task {task_id} is already reserved by {assigned}.")
            sys.exit(1)

        task["status"] = "in_progress"
        task["assigned_to"] = agent_id
        task["updated_at"] = now_iso()
        task["heartbeat_at"] = now_iso()
        save_db(db)
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
    in_progress = [task for task in tasks if str(task.get("status", "")).lower() == "in_progress"]
    available = [task for task in tasks if str(task.get("status", "")).lower() == "pending"]
    completed = [
        task
        for task in tasks
        if str(task.get("status", "")).lower() in {"completed", "done"}
    ]

    print(f"\nIN PROGRESS: {len(in_progress)}")
    for task in in_progress:
        assigned = _assignee(task) or "UNASSIGNED"
        print(f"  [{task['id']}] {task['title']} (Assigned: {assigned})")

    print(f"\nAVAILABLE: {len(available)}")
    for task in available[:5]:
        print(f"  [{task['id']}] {task['title']}")

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
