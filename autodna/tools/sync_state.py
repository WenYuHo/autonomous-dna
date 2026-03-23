"""
tools/sync_state.py
Modern State Sync for Autonomous-DNA.
Manages TASK_QUEUE.json: reserve, complete, status.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_FILE = Path("agent/TASK_QUEUE.json")

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def load_db():
    if not DB_FILE.exists():
        print(f"ERROR: {DB_FILE} not found.")
        sys.exit(1)
    try:
        return json.loads(DB_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: Failed to read {DB_FILE}: {e}")
        sys.exit(1)

def save_db(db):
    DB_FILE.write_text(json.dumps(db, indent=2), encoding="utf-8")

def reserve(task_id: int, agent_id: str):
    db = load_db()
    for t in db.get("tasks", []):
        if t.get("id") == task_id:
            if t.get("status") in {"completed", "done"}:
                print(f"ERROR: Task {task_id} is already completed.")
                sys.exit(1)
            assigned = t.get("assigned_to")
            if assigned and assigned != agent_id:
                print(f"ERROR: Task {task_id} is already reserved by {assigned}.")
                sys.exit(1)
            
            t["status"] = "in_progress"
            t["assigned_to"] = agent_id
            t["updated_at"] = now_iso()
            save_db(db)
            print(f"✅ Reserved Task #{task_id} for {agent_id}")
            return
    print(f"ERROR: Task {task_id} not found.")
    sys.exit(1)

def mark_done(task_id: int):
    db = load_db()
    for t in db.get("tasks", []):
        if t.get("id") == task_id:
            t["status"] = "completed"
            t["updated_at"] = now_iso()
            save_db(db)
            print(f"✅ Task #{task_id} marked as COMPLETED")
            return
    print(f"ERROR: Task {task_id} not found.")
    sys.exit(1)

def status():
    db = load_db()
    tasks = db.get("tasks", [])
    in_progress = [t for t in tasks if t.get("status") == "in_progress"]
    available = [t for t in tasks if t.get("status") == "pending"]
    completed = [t for t in tasks if t.get("status") in {"completed", "done"}]

    print(f"\nIN PROGRESS: {len(in_progress)}")
    for t in in_progress:
        print(f"  [{t['id']}] {t['title']} (Assigned: {t['assigned_to']})")
    
    print(f"\nAVAILABLE: {len(available)}")
    for t in available[:5]:
        print(f"  [{t['id']}] {t['title']}")
    
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
