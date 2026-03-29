"""
tools/session_start.py
Rehydrates agent context from TASK_QUEUE.md and MEMORY.md.
Run at the start of every session and whenever context seems degraded.

Output is designed to be read by the agent - structured for LLM consumption.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autodna.tools.memory_utils import read_memory_sections
from autodna.tools.recurring_issues import detect_recurring_issues

HEARTBEAT_TTL_SECONDS = int(os.getenv("AUTODNA_TASK_HEARTBEAT_TTL", "900"))


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


def _heartbeat_fresh(task: dict) -> bool:
    heartbeat = _parse_iso(task.get("heartbeat_at"))
    if not heartbeat:
        return False
    return datetime.now(timezone.utc) - heartbeat <= timedelta(seconds=HEARTBEAT_TTL_SECONDS)


def load_tasks_json(path: Path) -> tuple[list[dict], list[dict], list[dict]]:
    """Load tasks from JSON and split into active, claimable, and stale claimable buckets."""
    if not path.exists():
        return [], [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        tasks = data.get("tasks", [])
        in_progress = []
        available = []
        stale_claimable = []
        for task in tasks:
            status = str(task.get("status", "")).lower()
            if status == "in_progress":
                if _heartbeat_fresh(task):
                    in_progress.append(task)
                else:
                    stale_claimable.append(task)
                    available.append(task)
            elif status == "pending":
                available.append(task)
        return in_progress, available, stale_claimable
    except Exception:
        return [], [], []


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    root = Path.cwd()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("=" * 60)
    print(f"SESSION START - {now}")
    print("=" * 60)

    platform_file = root / "platform" / "ACTIVE"
    platform = platform_file.read_text().strip() if platform_file.exists() else "UNKNOWN"
    print(f"\nPLATFORM: {platform}")

    tq_json_path = root / "agent" / "TASK_QUEUE.json"
    if tq_json_path.exists():
        in_progress, available, stale_claimable = load_tasks_json(tq_json_path)
        print("\n--- IN PROGRESS ---")
        if in_progress:
            for task in in_progress:
                assignee = f" (Assigned: {task['assigned_to']})" if task.get("assigned_to") else ""
                print(f"[{task['id']}] {task['title']}{assignee}")
        else:
            print("(none)")

        if stale_claimable:
            print("\n--- STALE CLAIMABLE ---")
            for task in stale_claimable:
                assignee = f" (Last assigned: {task['assigned_to']})" if task.get("assigned_to") else ""
                print(f"[{task['id']}] {task['title']}{assignee}")

        print(f"\n--- BACKLOG: {len(available)} available task(s) ---")
        for task in available[:5]:
            stale = " [STALE]" if str(task.get("status", "")).lower() == "in_progress" else ""
            print(f"[{task['id']}] {task['title']}{stale}")
        if len(available) > 5:
            print(f"  ... and {len(available) - 5} more. Run 'python -m autodna.cli tasks list' for full list.")
    else:
        print("\nWARN: agent/TASK_QUEUE.json not found.")

    mem_path = root / "agent" / "MEMORY.md"
    if mem_path.exists():
        lines = mem_path.read_text(encoding="utf-8").splitlines()
        total = len([line for line in lines if line.strip() and not line.startswith("#")])
        print(f"\n--- MEMORY ({total} facts, limit 150) ---")
        facts = [line for line in lines if line.strip().startswith("- [")]
        for fact in facts[-20:]:
            print(fact)
        if total > 20:
            print(f"  ... {total - 20} older facts omitted. Read agent/MEMORY.md for full history.")
    else:
        print("\nWARN: agent/MEMORY.md not found. Run bridge.py to initialise.")

    sections = read_memory_sections(mem_path)
    if "Repo Organization" in sections:
        print("\n--- REPO ORGANIZATION ---")
        for line in sections["Repo Organization"]:
            print(line)

    try:
        outcomes_dir = root / "agent" / "run_outcomes"
        issues_db = root / "agent" / "issues.db"
        recurring = detect_recurring_issues(outcomes_dir, issues_db, persist=False)
        print("\n--- RECURRING ISSUES ---")
        if recurring:
            for issue in recurring:
                print(f"  [WARN] [{issue['count']}x] {issue['signature'][:100]}...")
        else:
            print("(none detected)")
    except Exception as exc:
        print(f"\n--- RECURRING ISSUES: not available ({exc}) ---")

    try:
        import importlib.util

        tl_path = root / "tools" / "trace_logger.py"
        spec = importlib.util.spec_from_file_location("trace_logger", tl_path)
        tl = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tl)
        latest = tl.get_latest_trace_file()
        if latest:
            entries = tl.read_trace()
            if entries:
                print("\n--- LAST SESSION ---")
                print(tl.format_summary(entries))
        sid = tl.new_session(platform.lower() if platform != "UNKNOWN" else "unknown")
        print(f"\n--- NEW SESSION: {sid} ---")
    except Exception:
        print("\n--- TRACING: not available (run from project root) ---")

    print("\n--- SKILL INDEX (load on demand only) ---")
    skills = {
        "git work (commit/PR/merge)": "skills/git/SKILL.md",
        "state sync (task/memory)": "skills/sync/SKILL.md",
        "research (library/API)": "skills/research/SKILL.md",
        "conflict resolution": "skills/conflict/SKILL.md",
        "context management": "skills/context/SKILL.md",
    }
    for label, path in skills.items():
        exists = "[OK]" if (root / path).exists() else "[XX]"
        print(f"  {exists}  {label:35s} -> {path}")

    print("\n--- HARD RULES REMINDER ---")
    print("NEVER edit scaffold files. NEVER mark done if tests fail.")
    print("NEVER force-push to main/master/develop.")
    print("IF context degraded -> re-run this script.")
    print("=" * 60)
    print("Ready. Pick the highest-priority unreserved task and begin.")
    print("=" * 60)


if __name__ == "__main__":
    main()
