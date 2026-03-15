"""
tools/trace_logger.py
Observability and tracing for Autonomous-DNA agent sessions.
Logs structured JSONL traces to agent/traces/<session-id>.jsonl.

Usage:
  python tools/trace_logger.py log --action <action> [--task-id N] [--files "a.py,b.py"] [--error "msg"]
  python tools/trace_logger.py summary [--session <session-id>]
  python tools/trace_logger.py new-session [--platform <name>]
"""

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

TRACES_DIR = Path("agent/traces")
CURRENT_SESSION_FILE = TRACES_DIR / ".current_session"

VALID_ACTIONS = {
    "session_start", "reserve", "plan", "implement",
    "verify", "done", "error", "skill_load",
}


def ensure_traces_dir() -> None:
    """Create traces directory if it doesn't exist."""
    TRACES_DIR.mkdir(parents=True, exist_ok=True)


def get_platform() -> str:
    """Detect platform from platform/ACTIVE file."""
    active = Path("platform/ACTIVE")
    if active.exists():
        return active.read_text().strip().lower()
    return "unknown"


def get_current_session() -> Optional[str]:
    """Read current session ID from file."""
    if CURRENT_SESSION_FILE.exists():
        return CURRENT_SESSION_FILE.read_text().strip()
    return None


def set_current_session(session_id: str) -> None:
    """Persist current session ID."""
    ensure_traces_dir()
    CURRENT_SESSION_FILE.write_text(session_id)


def new_session(platform: Optional[str] = None) -> str:
    """Start a new session and return the session ID."""
    session_id = uuid.uuid4().hex[:12]
    set_current_session(session_id)
    if platform is None:
        platform = get_platform()

    # Log session_start automatically
    log_action(
        session_id=session_id,
        action="session_start",
        platform=platform,
    )
    return session_id


def log_action(
    action: str,
    session_id: Optional[str] = None,
    platform: Optional[str] = None,
    task_id: Optional[int] = None,
    files_touched: Optional[list] = None,
    tool_count: Optional[int] = None,
    duration_seconds: Optional[float] = None,
    error: Optional[str] = None,
    meta: Optional[dict] = None,
) -> str:
    """Append a trace entry to the current session's JSONL file."""
    if action not in VALID_ACTIONS:
        print(f"ERROR: Invalid action '{action}'. Must be one of: {', '.join(sorted(VALID_ACTIONS))}")
        sys.exit(1)

    if session_id is None:
        session_id = get_current_session()
    if session_id is None:
        session_id = new_session(platform)

    if platform is None:
        platform = get_platform()

    entry = {
        "session_id": session_id,
        "platform": platform,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "action": action,
        "task_id": task_id,
        "files_touched": files_touched or [],
        "tool_count": tool_count,
        "duration_seconds": duration_seconds,
        "error": error,
        "meta": meta or {},
    }

    ensure_traces_dir()
    trace_file = TRACES_DIR / f"{session_id}.jsonl"
    with open(trace_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, separators=(",", ":")) + "\n")

    return session_id


def get_latest_trace_file() -> Optional[Path]:
    """Find the most recent trace file by modification time."""
    if not TRACES_DIR.exists():
        return None
    files = sorted(
        [f for f in TRACES_DIR.glob("*.jsonl")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def read_trace(session_id: Optional[str] = None) -> list:
    """Read all entries from a trace file."""
    if session_id:
        trace_file = TRACES_DIR / f"{session_id}.jsonl"
    else:
        trace_file = get_latest_trace_file()

    if not trace_file or not trace_file.exists():
        return []

    entries = []
    with open(trace_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def format_summary(entries: list) -> str:
    """Format trace entries as a human-readable summary."""
    if not entries:
        return "No trace data found."

    session_id = entries[0].get("session_id", "unknown")
    platform = entries[0].get("platform", "unknown")

    # Count actions
    action_counts = {}
    all_files = set()
    errors = []
    for e in entries:
        action = e.get("action", "unknown")
        action_counts[action] = action_counts.get(action, 0) + 1
        for f in e.get("files_touched", []):
            all_files.add(f)
        if e.get("error"):
            errors.append(e["error"])

    # Time span
    first_ts = entries[0].get("timestamp", "?")
    last_ts = entries[-1].get("timestamp", "?")

    lines = [
        f"Session: {session_id} ({platform})",
        f"Time: {first_ts} -> {last_ts}",
        f"Actions: {len(entries)} total",
    ]

    for action, count in sorted(action_counts.items()):
        lines.append(f"  {action}: {count}")

    if all_files:
        lines.append(f"Files touched: {len(all_files)}")
        for f in sorted(all_files)[:10]:
            lines.append(f"  {f}")
        if len(all_files) > 10:
            lines.append(f"  ... and {len(all_files) - 10} more")

    if errors:
        lines.append(f"Errors: {len(errors)}")
        for err in errors[:5]:
            lines.append(f"  ✗ {err[:80]}")

    return "\n".join(lines)


def cmd_log(args: list) -> None:
    """Handle the 'log' subcommand."""
    action = None
    task_id = None
    files = []
    error = None
    platform = None

    i = 0
    while i < len(args):
        if args[i] == "--action" and i + 1 < len(args):
            action = args[i + 1]
            i += 2
        elif args[i] == "--task-id" and i + 1 < len(args):
            task_id = int(args[i + 1])
            i += 2
        elif args[i] == "--files" and i + 1 < len(args):
            files = [f.strip() for f in args[i + 1].split(",") if f.strip()]
            i += 2
        elif args[i] == "--error" and i + 1 < len(args):
            error = args[i + 1]
            i += 2
        elif args[i] == "--platform" and i + 1 < len(args):
            platform = args[i + 1]
            i += 2
        else:
            print(f"Unknown argument: {args[i]}")
            sys.exit(1)

    if not action:
        print("ERROR: --action is required.")
        sys.exit(1)

    session_id = log_action(
        action=action,
        task_id=task_id,
        files_touched=files,
        error=error,
        platform=platform,
    )
    print(f"Logged: {action}" + (f" (task {task_id})" if task_id else "") + f" -> {session_id}")


def cmd_summary(args: list) -> None:
    """Handle the 'summary' subcommand."""
    session_id = None
    i = 0
    while i < len(args):
        if args[i] == "--session" and i + 1 < len(args):
            session_id = args[i + 1]
            i += 2
        else:
            i += 1

    entries = read_trace(session_id)
    print(format_summary(entries))


def cmd_new_session(args: list) -> None:
    """Handle the 'new-session' subcommand."""
    platform = None
    i = 0
    while i < len(args):
        if args[i] == "--platform" and i + 1 < len(args):
            platform = args[i + 1]
            i += 2
        else:
            i += 1

    session_id = new_session(platform)
    print(f"New session: {session_id}")


def main() -> None:
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0]
    rest = args[1:]

    if cmd == "log":
        cmd_log(rest)
    elif cmd == "summary":
        cmd_summary(rest)
    elif cmd == "new-session":
        cmd_new_session(rest)
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
