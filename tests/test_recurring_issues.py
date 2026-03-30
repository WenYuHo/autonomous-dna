import json
import sqlite3

from autodna.tools import recurring_issues
from autodna.tools import tasks as task_api


def _write_outcome(path, *, task_id=1, status="blocked", notes="Permission denied: C:\\secret\\gemini.cmd access is restricted."):
    path.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "status": status,
                "notes": notes,
                "agent": "autodna",
                "timestamp": "2026-03-27T05:11:22Z",
            }
        ),
        encoding="utf-8",
    )


def test_detect_recurring_issues_processes_each_outcome_file_once(tmp_path):
    outcomes_dir = tmp_path / "run_outcomes"
    outcomes_dir.mkdir()
    db_path = tmp_path / "issues.db"
    _write_outcome(outcomes_dir / "task_1_20260327T051122Z.json", task_id=1)
    _write_outcome(outcomes_dir / "task_2_20260327T051124Z.json", task_id=2)

    recurring = recurring_issues.detect_recurring_issues(outcomes_dir, db_path)

    assert recurring == [
        {
            "signature": "Permission denied: [PATH] access is restricted.",
            "count": 2,
        }
    ]

    recurring_again = recurring_issues.detect_recurring_issues(outcomes_dir, db_path)
    assert recurring_again == []

    conn = sqlite3.connect(db_path)
    try:
        issue_rows = conn.execute("SELECT signature, count FROM issues").fetchall()
        processed_rows = conn.execute("SELECT outcome_key FROM processed_outcomes").fetchall()
    finally:
        conn.close()

    assert issue_rows == [("Permission denied: [PATH] access is restricted.", 2)]
    assert sorted(row[0] for row in processed_rows) == [
        "task_1_20260327T051122Z.json",
        "task_2_20260327T051124Z.json",
    ]


def test_detect_recurring_issues_preview_mode_is_read_only(tmp_path):
    outcomes_dir = tmp_path / "run_outcomes"
    outcomes_dir.mkdir()
    db_path = tmp_path / "issues.db"
    _write_outcome(outcomes_dir / "task_1_20260327T051122Z.json", task_id=1)
    _write_outcome(outcomes_dir / "task_2_20260327T051124Z.json", task_id=2)

    recurring = recurring_issues.detect_recurring_issues(outcomes_dir, db_path, persist=False)

    assert recurring == [
        {
            "signature": "Permission denied: [PATH] access is restricted.",
            "count": 2,
        }
    ]
    assert not db_path.exists()


def test_auto_create_fix_tasks_dedupes_duplicate_signatures(tmp_path, monkeypatch):
    queue_path = tmp_path / "TASK_QUEUE.json"
    queue_path.write_text(json.dumps({"tasks": []}), encoding="utf-8")
    monkeypatch.setattr(task_api, "DB_FILE", queue_path)

    recurring = [
        {"signature": "Permission denied: [PATH] access is restricted.", "count": 2},
        {"signature": "Permission denied: [PATH] access is restricted.", "count": 3},
    ]

    recurring_issues.auto_create_fix_tasks(recurring, queue_path)

    data = json.loads(queue_path.read_text(encoding="utf-8"))
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["title"] == "[FIX] Recurring Issue: Permission denied: [PATH] access is restricted...."
    assert "Count: 3" in data["tasks"][0]["description"]
