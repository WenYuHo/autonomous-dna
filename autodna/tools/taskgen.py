import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


DEFAULT_QUEUE_PATH = Path("agent/TASK_QUEUE.json")
DEFAULT_ARTIFACT_DIR = Path("agent/skills/auto_generated")


def load_queue(path: Path) -> dict:
    if not path.exists():
        return {"tasks": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_queue(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _task_by_id(tasks: list[dict]) -> dict:
    return {t.get("id"): t for t in tasks if isinstance(t.get("id"), int)}


def _is_blocked(task: dict, by_id: dict) -> bool:
    blocked_by = task.get("blocked_by")
    if blocked_by is None:
        return False
    blocker = by_id.get(blocked_by)
    if not blocker:
        return False
    return blocker.get("status") not in ("done", "info")


def has_actionable_tasks(tasks: list[dict]) -> bool:
    by_id = _task_by_id(tasks)
    for task in tasks:
        if task.get("status") != "pending":
            continue
        title = task.get("title", "")
        if title.strip().upper().startswith("CYCLE"):
            continue
        if _is_blocked(task, by_id):
            continue
        return True
    return False


def max_task_id(tasks: list[dict]) -> int:
    ids = [t.get("id") for t in tasks if isinstance(t.get("id"), int)]
    return max(ids) if ids else 0


def max_cycle_number(tasks: list[dict]) -> int:
    max_cycle = 0
    for task in tasks:
        cycle_val = task.get("cycle")
        if isinstance(cycle_val, int):
            max_cycle = max(max_cycle, cycle_val)
        title = task.get("title", "")
        match = re.search(r"cycle\s+(\d+)", title, re.IGNORECASE)
        if match:
            try:
                max_cycle = max(max_cycle, int(match.group(1)))
            except ValueError:
                pass
    return max_cycle


def find_latest_artifact(dir_path: Path) -> Optional[Path]:
    if not dir_path.exists():
        return None
    candidates = sorted(
        [p for p in dir_path.glob("*.md") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def build_cycle_tasks(
    start_id: int,
    cycle_number: int,
    artifact_path: Optional[Path],
) -> list[dict]:
    artifact_ref = str(artifact_path) if artifact_path else "NONE"
    now = get_now()

    cycle_id = start_id
    research_id = start_id + 1
    improve_id = start_id + 2
    eval_id = start_id + 3

    cycle_task = {
        "id": cycle_id,
        "title": f"CYCLE {cycle_number} — AUTOGEN: Research Synthesis",
        "description": "Auto-generated cycle to turn research into actionable improvements.",
        "ref": artifact_ref,
        "status": "info",
        "assigned_to": None,
        "updated_at": now,
        "cycle": cycle_number,
    }

    research_task = {
        "id": research_id,
        "title": "[RESEARCH] Synthesize improvements from latest research",
        "description": (
            "Review the latest research artifact and extract 3 candidate improvements. "
            "For each, include the evidence/source, expected benefit, and an initial test plan. "
            "Update the IMPROVE/EVAL tasks below with concrete acceptance criteria."
        ),
        "ref": artifact_ref,
        "status": "pending",
        "assigned_to": None,
        "updated_at": now,
        "cycle": cycle_number,
    }

    improve_task = {
        "id": improve_id,
        "title": "[IMPROVE] Implement highest-value improvement",
        "description": (
            "Implement the top-ranked improvement from the synthesis task. "
            "Update tests and docs as needed. Run the test suite before marking done."
        ),
        "ref": artifact_ref,
        "status": "pending",
        "assigned_to": None,
        "updated_at": now,
        "blocked_by": research_id,
        "cycle": cycle_number,
    }

    eval_task = {
        "id": eval_id,
        "title": "[EVAL] Validate improvement impact",
        "description": (
            "Evaluate the implemented improvement using existing eval tools or reports. "
            "Record results in agent/reports and note whether to keep or revert."
        ),
        "ref": artifact_ref,
        "status": "pending",
        "assigned_to": None,
        "updated_at": now,
        "blocked_by": improve_id,
        "cycle": cycle_number,
    }

    return [cycle_task, research_task, improve_task, eval_task]


def run_taskgen(
    queue_path: Path,
    artifact_path: Optional[Path],
    if_empty: bool,
    dry_run: bool,
) -> Tuple[bool, int]:
    db = load_queue(queue_path)
    tasks = db.get("tasks", [])

    if if_empty and has_actionable_tasks(tasks):
        return False, 0

    artifact = artifact_path or find_latest_artifact(DEFAULT_ARTIFACT_DIR)
    cycle_number = max_cycle_number(tasks) + 1
    start_id = max_task_id(tasks) + 1
    new_tasks = build_cycle_tasks(start_id, cycle_number, artifact)

    if dry_run:
        return True, len(new_tasks)

    db.setdefault("tasks", []).extend(new_tasks)
    save_queue(queue_path, db)
    return True, len(new_tasks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous DNA Task Generator")
    parser.add_argument(
        "--queue",
        default=str(DEFAULT_QUEUE_PATH),
        help="Path to TASK_QUEUE.json",
    )
    parser.add_argument(
        "--artifact",
        default=None,
        help="Path to research artifact (default: latest in agent/skills/auto_generated)",
    )
    parser.add_argument(
        "--if-empty",
        action="store_true",
        help="Only generate tasks when no actionable pending tasks exist",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without writing")

    args = parser.parse_args()
    queue_path = Path(args.queue)
    artifact_path = Path(args.artifact) if args.artifact else None

    created, count = run_taskgen(queue_path, artifact_path, args.if_empty, args.dry_run)
    if not created:
        print("Actionable tasks already exist. Skipping task generation.")
        return
    if args.dry_run:
        print(f"[DRY RUN] Would add {count} task(s) to {queue_path}")
        return
    print(f"Added {count} task(s) to {queue_path}")


if __name__ == "__main__":
    main()
