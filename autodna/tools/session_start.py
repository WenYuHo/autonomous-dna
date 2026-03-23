"""
tools/session_start.py
Rehydrates agent context from TASK_QUEUE.md and MEMORY.md.
Run at the start of every session and whenever context seems degraded.

Output is designed to be read by the agent — structured for LLM consumption.
"""

from pathlib import Path
from datetime import datetime, timezone

# Fix Windows cp1252 charmap encoding for console emojis
# This block is moved inside main() as per the instruction's implied structure.

import json

def load_tasks_json(path: Path) -> tuple[list[dict], list[dict]]:
    """Load tasks from JSON and split into in-progress and available."""
    if not path.exists():
        return [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        tasks = data.get("tasks", [])
        in_progress = [t for t in tasks if t.get("status") == "in_progress"]
        available = [t for t in tasks if t.get("status") == "pending"]
        return in_progress, available
    except Exception:
        return [], []


def main() -> None:
    root = Path.cwd()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("=" * 60)
    print(f"SESSION START — {now}")
    print("=" * 60)

    # --- Platform ---
    platform_file = root / "platform" / "ACTIVE"
    platform = platform_file.read_text().strip() if platform_file.exists() else "UNKNOWN"
    print(f"\nPLATFORM: {platform}")

    # --- Tasks ---
    tq_json_path = root / "agent" / "TASK_QUEUE.json"
    if tq_json_path.exists():
        in_progress, available = load_tasks_json(tq_json_path)
        print("\n--- IN PROGRESS ---")
        if in_progress:
            for t in in_progress:
                assignee = f" (Assigned: {t['assigned_to']})" if t.get('assigned_to') else ""
                print(f"[{t['id']}] {t['title']}{assignee}")
        else:
            print("(none)")

        print(f"\n--- BACKLOG: {len(available)} available task(s) ---")
        for t in available[:5]:
            print(f"[{t['id']}] {t['title']}")
        if len(available) > 5:
            print(f"  ... and {len(available) - 5} more. Run 'python -m autodna.cli tasks list' for full list.")
    else:
        print("\nWARN: agent/TASK_QUEUE.json not found.")

    # --- Memory snapshot ---
    mem_path = root / "agent" / "MEMORY.md"
    if mem_path.exists():
        lines = mem_path.read_text().splitlines()
        total = len([line for line in lines if line.strip() and not line.startswith("#")])
        print(f"\n--- MEMORY ({total} facts, limit 150) ---")
        # Show most recent 20 facts
        facts = [line for line in lines if line.strip().startswith("- [")]
        for fact in facts[-20:]:
            print(fact)
        if total > 20:
            print(f"  ... {total - 20} older facts omitted. Read agent/MEMORY.md for full history.")
    else:
        print("\nWARN: agent/MEMORY.md not found. Run bridge.py to initialise.")

    # --- Last session trace ---
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
        # Start a new trace session
        sid = tl.new_session(platform.lower() if platform != "UNKNOWN" else "unknown")
        print(f"\n--- NEW SESSION: {sid} ---")
    except Exception:
        # Tracing is optional — don't block session start
        print("\n--- TRACING: not available (run from project root) ---")

    # --- Skill index reminder ---
    print("\n--- SKILL INDEX (load on demand only) ---")
    skills = {
        "git work (commit/PR/merge)": "skills/git/SKILL.md",
        "state sync (task/memory)":   "skills/sync/SKILL.md",
        "research (library/API)":     "skills/research/SKILL.md",
        "conflict resolution":        "skills/conflict/SKILL.md",
        "context management":         "skills/context/SKILL.md",
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
