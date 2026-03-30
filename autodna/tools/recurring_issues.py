import json
import sqlite3
import re
from pathlib import Path
from datetime import datetime, timezone

def _normalize_error(error_msg: str) -> str:
    """Strips paths, task IDs, and timestamps to get a stable error signature."""
    if not error_msg:
        return "Unknown Error"
    # Remove paths
    res = re.sub(r"[a-zA-Z]:\\[^\s]+", "[PATH]", error_msg)
    # Remove timestamps like 2026-03-27T05:11:22Z
    res = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", "[TIMESTAMP]", res)
    # Remove task IDs like Task #1
    res = re.sub(r"Task #\d+", "Task #[ID]", res)
    # Remove memory addresses
    res = re.sub(r"0x[0-9a-fA-F]+", "[ADDR]", res)
    return res.strip()


def scan_outcomes(outcomes_dir: Path) -> list[dict]:
    """Finds all blocked or error outcomes in the specified directory."""
    if not outcomes_dir.exists():
        return []

    outcomes = []
    for f in sorted(outcomes_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("status") in ("blocked", "error"):
                outcomes.append(data)
        except Exception:
            continue
    return outcomes


def _iter_error_outcomes(outcomes_dir: Path):
    for outcome_file in sorted(outcomes_dir.glob("*.json")):
        try:
            data = json.loads(outcome_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("status") in ("blocked", "error"):
            yield outcome_file.name, data


def _create_schema(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signature TEXT UNIQUE,
            count INTEGER DEFAULT 1,
            last_hit_at TEXT,
            fix_task_id INTEGER
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS processed_outcomes (
            outcome_key TEXT PRIMARY KEY,
            signature TEXT,
            processed_at TEXT
        )
        """
    )


def _preview_recurring_issues(outcomes_dir: Path) -> list[dict]:
    counts: dict[str, int] = {}
    for _outcome_key, outcome in _iter_error_outcomes(outcomes_dir):
        signature = _normalize_error(outcome.get("notes") or outcome.get("error"))
        counts[signature] = counts.get(signature, 0) + 1
    return [
        {"signature": signature, "count": count}
        for signature, count in counts.items()
        if count >= 2
    ]


def detect_recurring_issues(outcomes_dir: Path, db_path: Path, persist: bool = True):
    """Detects recurring issues (seen 2+ times).

    When ``persist`` is true, only newly seen blocked/error outcomes are counted and
    recorded in SQLite so self-improve does not repeatedly re-ingest the same files.
    When ``persist`` is false, the function is read-only and reports recurring
    signatures from the outcome directory without mutating any state.
    """
    if not outcomes_dir.exists():
        return []
    if not persist:
        return _preview_recurring_issues(outcomes_dir)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    _create_schema(cursor)
    conn.commit()

    processed_outcomes = {
        row[0]
        for row in cursor.execute("SELECT outcome_key FROM processed_outcomes")
    }

    recurring_by_signature: dict[str, int] = {}
    for outcome_key, outcome in _iter_error_outcomes(outcomes_dir):
        if outcome_key in processed_outcomes:
            continue

        signature = _normalize_error(outcome.get("notes") or outcome.get("error"))
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        cursor.execute("SELECT id, count FROM issues WHERE signature = ?", (signature,))
        row = cursor.fetchone()
        if row:
            issue_id, count = row
            new_count = count + 1
            cursor.execute(
                "UPDATE issues SET count = ?, last_hit_at = ? WHERE id = ?",
                (new_count, now, issue_id),
            )
        else:
            new_count = 1
            cursor.execute(
                "INSERT INTO issues (signature, count, last_hit_at) VALUES (?, ?, ?)",
                (signature, new_count, now),
            )

        cursor.execute(
            "INSERT OR REPLACE INTO processed_outcomes (outcome_key, signature, processed_at) VALUES (?, ?, ?)",
            (outcome_key, signature, now),
        )
        processed_outcomes.add(outcome_key)

        if new_count >= 2:
            previous_count = recurring_by_signature.get(signature, 0)
            recurring_by_signature[signature] = max(previous_count, new_count)

    conn.commit()
    conn.close()
    return [
        {"signature": signature, "count": count}
        for signature, count in recurring_by_signature.items()
    ]

def auto_create_fix_tasks(recurring_issues: list[dict], queue_path: Path):
    """Creates [FIX] tasks for recurring issues if they don't already exist."""
    if not recurring_issues or not queue_path.exists():
        return

    from autodna.tools.tasks import add_task, load_db
    db = load_db()
    existing_titles = {t.get("title", "") for t in db.get("tasks", [])}
    latest_by_signature: dict[str, dict] = {}

    for issue in recurring_issues:
        signature = issue.get("signature")
        if not signature:
            continue
        current = latest_by_signature.get(signature)
        if current is None or issue.get("count", 0) > current.get("count", 0):
            latest_by_signature[signature] = issue

    for issue in latest_by_signature.values():
        title = f"[FIX] Recurring Issue: {issue['signature'][:50]}..."
        if title in existing_titles:
            continue
        add_task(
            title=title,
            description=f"Automated fix request for recurring error: {issue['signature']}. Count: {issue['count']}"
        )
        existing_titles.add(title)
