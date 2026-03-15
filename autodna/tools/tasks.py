import json
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Fix Windows cp1252 encoding for emoji output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DB_FILE = Path("agent/TASK_QUEUE.json")

def load_db():
    if not DB_FILE.exists():
        return {"tasks": []}
    return json.loads(DB_FILE.read_text(encoding="utf-8"))

def save_db(db):
    DB_FILE.write_text(json.dumps(db, indent=2), encoding="utf-8")

def get_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def add_task(title, description, ref="NONE"):
    db = load_db()
    new_id = len(db["tasks"]) + 1
    db["tasks"].append({
        "id": new_id,
        "title": title,
        "description": description,
        "ref": ref,
        "status": "pending",
        "assigned_to": None,
        "updated_at": get_now()
    })
    save_db(db)
    print(f"✅ Added Task #{new_id}: {title}")

def list_tasks(status_filter=None):
    db = load_db()
    tasks = db["tasks"]
    if status_filter:
        tasks = [t for t in tasks if t["status"] == status_filter]

    if not tasks:
        print("📭 No tasks found matching criteria.")
        return

    for t in tasks:
        assignee = f" (Assigned: {t['assigned_to']})" if t['assigned_to'] else ""
        print(f"[{t['id']}] {t['title']} - {t['status'].upper()}{assignee}")
        print(f"    > {t['description']}")

def claim_task(task_id, agent_name):
    db = load_db()
    for t in db["tasks"]:
        if t["id"] == task_id:
            if t["status"] == "completed":
                print(f"❌ Task #{task_id} is already completed.")
                return
            t["status"] = "in_progress"
            t["assigned_to"] = agent_name
            t["updated_at"] = get_now()
            save_db(db)
            print(f"✅ {agent_name} successfully claimed Task #{task_id}!")
            return
    print(f"❌ Task #{task_id} not found.")

def complete_task(task_id):
    db = load_db()
    for t in db["tasks"]:
        if t["id"] == task_id:
            t["status"] = "completed"
            t["updated_at"] = get_now()
            save_db(db)
            print(f"✅ Task #{task_id} marked as COMPLETED!")
            return
    print(f"❌ Task #{task_id} not found.")

def init_db_from_md():
    """Converts the deprecated TASK_QUEUE.md into the new JSON DB."""
    md_file = Path("agent/TASK_QUEUE.md")
    if not md_file.exists():
        return

    db = {"tasks": []}
    lines = md_file.read_text(encoding="utf-8").splitlines()

    current_task = None
    task_id_counter = 1

    for line in lines:
        if line.startswith("- [ ] **") or line.startswith("- [x] **"):
            is_completed = "[x]" in line
            title = line.split("**")[1]
            current_task = {
                "id": task_id_counter,
                "title": title,
                "description": "",
                "ref": "NONE",
                "status": "completed" if is_completed else "pending",
                "assigned_to": None,
                "updated_at": get_now()
            }
            db["tasks"].append(current_task)
            task_id_counter += 1
        elif current_task and line.strip().startswith("- Task:"):
            current_task["description"] = line.split("Task:")[1].strip()
        elif current_task and line.strip().startswith("- Ref:"):
            current_task["ref"] = line.split("Ref:")[1].strip()
        elif current_task and line.strip().startswith("- Reserved:") and "NONE" not in line:
            current_task["assigned_to"] = line.split("Reserved:")[1].split("@")[0].strip()
            if not is_completed:
                current_task["status"] = "in_progress"

    save_db(db)
    print(f"✅ Migrated {len(db['tasks'])} tasks from Markdown to JSON DB.")
    # Deprecate the old file to prevent agents reading it
    if md_file.exists():
        md_file.rename("agent/TASK_QUEUE.deprecated.md")

def main():
    parser = argparse.ArgumentParser(description="Symphony V3 Task API")
    subparsers = parser.add_subparsers(dest="action", help="Action to perform")

    # Init
    subparsers.add_parser("init", help="Convert TASK_QUEUE.md to JSON")

    # List
    parser_list = subparsers.add_parser("list", help="List tasks")
    parser_list.add_argument("--status", choices=["pending", "in_progress", "completed"], help="Filter by status")

    # Add
    parser_add = subparsers.add_parser("add", help="Add a new task")
    parser_add.add_argument("title", help="Task title")
    parser_add.add_argument("description", help="Task details")

    # Claim
    parser_claim = subparsers.add_parser("claim", help="Claim a task")
    parser_claim.add_argument("id", type=int, help="Task ID")
    parser_claim.add_argument("agent", help="Agent claiming the task (e.g. worker-1)")

    # Complete
    parser_complete = subparsers.add_parser("complete", help="Complete a task")
    parser_complete.add_argument("id", type=int, help="Task ID")

    args = parser.parse_args()

    if args.action == "init":
        init_db_from_md()
    elif args.action == "list":
        list_tasks(args.status)
    elif args.action == "add":
        add_task(args.title, args.description)
    elif args.action == "claim":
        claim_task(args.id, args.agent)
    elif args.action == "complete":
        complete_task(args.id)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
