import json
from pathlib import Path

from autodna.tools import tasks


def _write_db(path: Path, tasks_list: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"tasks": tasks_list}, indent=2), encoding="utf-8")


def _load_db(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_claim_task_assigns_when_pending(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "agent" / "TASK_QUEUE.json"
    _write_db(
        db_path,
        [
            {
                "id": 1,
                "title": "Test",
                "description": "desc",
                "ref": "NONE",
                "status": "pending",
                "assigned_to": None,
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(tasks, "DB_FILE", db_path)

    tasks.claim_task(1, "agent-a")
    out = capsys.readouterr().out
    assert "successfully claimed" in out

    db = _load_db(db_path)
    assert db["tasks"][0]["status"] == "in_progress"
    assert db["tasks"][0]["assigned_to"] == "agent-a"
    assert db["tasks"][0]["heartbeat_at"].endswith("Z")


def test_claim_task_rejects_other_agent(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "agent" / "TASK_QUEUE.json"
    _write_db(
        db_path,
        [
            {
                "id": 2,
                "title": "Test",
                "description": "desc",
                "ref": "NONE",
                "status": "in_progress",
                "assigned_to": "agent-a",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(tasks, "DB_FILE", db_path)

    tasks.claim_task(2, "agent-b")
    out = capsys.readouterr().out
    assert "already claimed by agent-a" in out

    db = _load_db(db_path)
    assert db["tasks"][0]["assigned_to"] == "agent-a"
    assert db["tasks"][0]["status"] == "in_progress"


def test_claim_task_idempotent_same_agent(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "agent" / "TASK_QUEUE.json"
    _write_db(
        db_path,
        [
            {
                "id": 3,
                "title": "Test",
                "description": "desc",
                "ref": "NONE",
                "status": "in_progress",
                "assigned_to": "agent-a",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(tasks, "DB_FILE", db_path)

    tasks.claim_task(3, "agent-a")
    out = capsys.readouterr().out
    assert "already has Task #3 claimed" in out

    db = _load_db(db_path)
    assert db["tasks"][0]["assigned_to"] == "agent-a"
    assert db["tasks"][0]["status"] == "in_progress"


def test_claim_task_rejects_completed(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "agent" / "TASK_QUEUE.json"
    _write_db(
        db_path,
        [
            {
                "id": 4,
                "title": "Test",
                "description": "desc",
                "ref": "NONE",
                "status": "completed",
                "assigned_to": "agent-a",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(tasks, "DB_FILE", db_path)

    tasks.claim_task(4, "agent-b")
    out = capsys.readouterr().out
    assert "already completed" in out

    db = _load_db(db_path)
    assert db["tasks"][0]["status"] == "completed"


def test_complete_task_updates_heartbeat(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "agent" / "TASK_QUEUE.json"
    _write_db(
        db_path,
        [
            {
                "id": 5,
                "title": "Test",
                "description": "desc",
                "ref": "NONE",
                "status": "in_progress",
                "assigned_to": "agent-a",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(tasks, "DB_FILE", db_path)

    tasks.complete_task(5)
    out = capsys.readouterr().out
    assert "marked as COMPLETED" in out

    db = _load_db(db_path)
    assert db["tasks"][0]["status"] == "completed"
    assert db["tasks"][0]["heartbeat_at"].endswith("Z")


def test_claim_task_recovers_orphaned_in_progress(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "agent" / "TASK_QUEUE.json"
    _write_db(
        db_path,
        [
            {
                "id": 6,
                "title": "Recovered task",
                "description": "desc",
                "ref": "NONE",
                "status": "in_progress",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(tasks, "DB_FILE", db_path)

    tasks.claim_task(6, "agent-a")
    out = capsys.readouterr().out
    assert "resumed orphaned Task #6" in out

    db = _load_db(db_path)
    assert db["tasks"][0]["assigned_to"] == "agent-a"
    assert db["tasks"][0]["heartbeat_at"].endswith("Z")


def test_list_tasks_handles_missing_assigned_to(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "agent" / "TASK_QUEUE.json"
    _write_db(
        db_path,
        [
            {
                "id": 7,
                "title": "Unassigned task",
                "description": "desc",
                "ref": "NONE",
                "status": "in_progress",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(tasks, "DB_FILE", db_path)

    tasks.list_tasks()
    out = capsys.readouterr().out
    assert "Unassigned task - IN_PROGRESS" in out
