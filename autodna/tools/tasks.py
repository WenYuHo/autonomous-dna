import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Fix Windows cp1252 encoding for CLI output.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DB_FILE = Path("agent/TASK_QUEUE.json")


def load_db():
    if not DB_FILE.exists():
        return {"tasks": []}
    return json.loads(DB_FILE.read_text(encoding="utf-8"))


def save_db(db):
    DB_FILE.write_text(json.dumps(db, indent=2), encoding="utf-8")


def get_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _assignee(task):
    assigned_to = task.get("assigned_to")
    if isinstance(assigned_to, str):
        assigned_to = assigned_to.strip()
    return assigned_to or None


def add_task(title, description, ref="NONE"):
    db = load_db()
    new_id = len(db["tasks"]) + 1
    db["tasks"].append(
        {
            "id": new_id,
            "title": title,
            "description": description,
            "ref": ref,
            "status": "pending",
            "assigned_to": None,
            "updated_at": get_now(),
        }
    )
    save_db(db)
    print(f"Added Task #{new_id}: {title}")


def list_tasks(status_filter=None):
    db = load_db()
    tasks = db.get("tasks", [])
    if status_filter:
        tasks = [t for t in tasks if t.get("status") == status_filter]

    if not tasks:
        print("No tasks found matching criteria.")
        return

    for task in tasks:
        assigned_to = _assignee(task)
        assignee = f" (Assigned: {assigned_to})" if assigned_to else ""
        print(f"[{task['id']}] {task['title']} - {str(task.get('status', '')).upper()}{assignee}")
        print(f"    > {task.get('description', '')}")


def claim_task(task_id, agent_name):
    db = load_db()
    for task in db.get("tasks", []):
        if task.get("id") != task_id:
            continue

        status = str(task.get("status", "")).lower()
        if status in {"completed", "done"}:
            print(f"Task #{task_id} is already completed.")
            return

        assigned_to = _assignee(task)
        if assigned_to and assigned_to != agent_name:
            print(f"Task #{task_id} is already claimed by {assigned_to}.")
            return

        if status == "in_progress" and not assigned_to:
            task["assigned_to"] = agent_name
            task["updated_at"] = get_now()
            task["heartbeat_at"] = get_now()
            save_db(db)
            print(f"{agent_name} resumed orphaned Task #{task_id}.")
            return

        if status == "in_progress":
            if assigned_to == agent_name:
                print(f"{agent_name} already has Task #{task_id} claimed.")
            else:
                print(f"Task #{task_id} is already in progress.")
            return

        task["status"] = "in_progress"
        task["assigned_to"] = agent_name
        task["updated_at"] = get_now()
        task["heartbeat_at"] = get_now()
        save_db(db)
        print(f"{agent_name} successfully claimed Task #{task_id}!")
        return

    print(f"Task #{task_id} not found.")


def complete_task(task_id, notes=None):
    db = load_db()
    for task in db.get("tasks", []):
        if task.get("id") != task_id:
            continue
        task["status"] = "completed"
        if notes:
            task["notes"] = notes
        task["updated_at"] = get_now()
        task["heartbeat_at"] = get_now()
        save_db(db)
        print(f"Task #{task_id} marked as COMPLETED!")
        return
    print(f"Task #{task_id} not found.")


def fail_task(task_id, notes=None):
    db = load_db()
    for task in db.get("tasks", []):
        if task.get("id") != task_id:
            continue
        task["status"] = "error"
        if notes:
            task["notes"] = notes
        task["updated_at"] = get_now()
        task["heartbeat_at"] = get_now()
        save_db(db)
        print(f"Task #{task_id} marked as ERROR!")
        return
    print(f"Task #{task_id} not found.")


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
                "updated_at": get_now(),
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
    print(f"Migrated {len(db['tasks'])} tasks from Markdown to JSON DB.")
    if md_file.exists():
        md_file.rename("agent/TASK_QUEUE.deprecated.md")


def get_next_task():
    """Returns the next actionable task (pending or retryable error)."""
    db = load_db()
    tasks = db.get("tasks", [])
    by_id = {task.get("id"): task for task in tasks}

    def is_blocked(task):
        blocked_by = task.get("blocked_by")
        if not blocked_by:
            return False
        blocker = by_id.get(blocked_by)
        if not blocker:
            return False
        return str(blocker.get("status", "")).lower() not in {"completed", "done", "info"}

    for task in tasks:
        if str(task.get("status", "")).lower() == "pending" and not is_blocked(task):
            if not task.get("title", "").strip().upper().startswith("CYCLE"):
                return task

    for task in tasks:
        if str(task.get("status", "")).lower() in {"error", "blocked"} and not is_blocked(task):
            if not task.get("title", "").strip().upper().startswith("CYCLE"):
                return task
    return None


def main():
    parser = argparse.ArgumentParser(description="Symphony V3 Task API")
    subparsers = parser.add_subparsers(dest="action", help="Action to perform")

    subparsers.add_parser("init", help="Convert TASK_QUEUE.md to JSON")

    parser_list = subparsers.add_parser("list", help="List tasks")
    parser_list.add_argument("--status", choices=["pending", "in_progress", "completed"], help="Filter by status")

    parser_add = subparsers.add_parser("add", help="Add a new task")
    parser_add.add_argument("title", help="Task title")
    parser_add.add_argument("description", help="Task details")

    parser_claim = subparsers.add_parser("claim", help="Claim a task")
    parser_claim.add_argument("id", type=int, help="Task ID")
    parser_claim.add_argument("agent", help="Agent claiming the task (e.g. autodna)")

    parser_complete = subparsers.add_parser("complete", help="Complete a task")
    parser_complete.add_argument("id", type=int, help="Task ID")
    parser_complete.add_argument("--notes", help="Optional completion notes")

    parser_done = subparsers.add_parser("mark-done", help="Alias for complete")
    parser_done.add_argument("id", type=int, help="Task ID")
    parser_done.add_argument("--notes", help="Optional completion notes")

    parser_error = subparsers.add_parser("mark-error", help="Mark a task as failed")
    parser_error.add_argument("id", type=int, help="Task ID")
    parser_error.add_argument("--notes", help="Optional error notes")

    subparsers.add_parser("next", help="Get the next actionable task (Linear Mode)")

    args = parser.parse_args()

    if args.action == "init":
        init_db_from_md()
    elif args.action == "list":
        list_tasks(args.status)
    elif args.action == "add":
        add_task(args.title, args.description)
    elif args.action == "claim":
        claim_task(args.id, args.agent)
    elif args.action in {"complete", "mark-done"}:
        complete_task(args.id, args.notes)
    elif args.action == "mark-error":
        fail_task(args.id, args.notes)
    elif args.action == "next":
        task = get_next_task()
        print(json.dumps(task) if task else "null")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
