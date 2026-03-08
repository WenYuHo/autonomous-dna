"""
tools/sync_state.py
Manages TASK_QUEUE.md state: reserve, complete, status.

Usage:
  python tools/sync_state.py TASK_ID --reserve AgentID
  python tools/sync_state.py TASK_ID --done
  python tools/sync_state.py --status
"""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path


QUEUE_FILE = Path("agent/TASK_QUEUE.md")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read() -> str:
    if not QUEUE_FILE.exists():
        print("ERROR: agent/TASK_QUEUE.md not found. Run bridge.py first.")
        sys.exit(1)
    return QUEUE_FILE.read_text()


def write(content: str) -> None:
    QUEUE_FILE.write_text(content)


def reserve(task_id: str, agent_id: str) -> None:
    content = read()

    # Check if already reserved by someone else
    pattern = rf"(- \[ \] {re.escape(task_id)}.*?Reserved:\s*)(\S+)"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        print(f"ERROR: Task '{task_id}' not found in TASK_QUEUE.md.")
        sys.exit(1)

    current_reserved = match.group(2)
    if current_reserved != "NONE":
        print(f"ERROR: Task '{task_id}' is already reserved by '{current_reserved}'. Pick a different task.")
        sys.exit(1)

    # Reserve it
    replacement = f"{match.group(1)}{agent_id} @ {now_iso()}"
    updated = content[:match.start()] + replacement + content[match.end():]
    write(updated)
    print(f"Reserved '{task_id}' for {agent_id}.")


def done(task_id: str) -> None:
    content = read()

    # Mark checkbox done
    updated = re.sub(
        rf"(- \[ \] )({re.escape(task_id)}:)",
        r"- [x] \2",
        content,
    )
    if updated == content:
        print(f"ERROR: Task '{task_id}' not found or already done.")
        sys.exit(1)

    # Fill Done timestamp
    updated = re.sub(
        rf"(- \[x\] {re.escape(task_id)}.*?Done:\s*)NONE",
        rf"\g<1>{now_iso()}",
        updated,
        flags=re.DOTALL,
    )

    write(updated)
    print(f"Marked '{task_id}' as done at {now_iso()}.")


def status() -> None:
    content = read()
    lines = content.splitlines()

    in_progress = []
    backlog_available = []
    backlog_blocked = []
    done_tasks = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- [ ]"):
            if "BlockedBy: NONE" in line or "BlockedBy:" not in line:
                if "Reserved: NONE" in line:
                    backlog_available.append(stripped)
                else:
                    in_progress.append(stripped)
            else:
                backlog_blocked.append(stripped)
        elif stripped.startswith("- [x]"):
            done_tasks.append(stripped)

    print(f"\nIN PROGRESS: {len(in_progress)}")
    for t in in_progress:
        print(f"  {t}")

    print(f"\nAVAILABLE: {len(backlog_available)}")
    for t in backlog_available[:5]:
        print(f"  {t}")

    print(f"\nBLOCKED: {len(backlog_blocked)}")
    print(f"DONE: {len(done_tasks)}")


def main() -> None:
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(0)

    if args[0] == "--status":
        status()
        return

    if len(args) < 2:
        print("Usage: sync_state.py TASK_ID --reserve AgentID | --done")
        sys.exit(1)

    task_id = args[0]

    if args[1] == "--reserve":
        if len(args) < 3:
            print("Usage: sync_state.py TASK_ID --reserve AgentID")
            sys.exit(1)
        reserve(task_id, args[2])

    elif args[1] == "--done":
        done(task_id)

    else:
        print(f"Unknown flag: {args[1]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
