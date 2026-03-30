import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _load_sync_state_module():
    module_path = Path(__file__).resolve().parents[1] / "tools" / "sync_state.py"
    spec = importlib.util.spec_from_file_location("sync_state_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_db(path: Path, tasks_list: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"tasks": tasks_list}, indent=2), encoding="utf-8")


def _load_db(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_reserve_reclaims_stale_assignment(tmp_path, monkeypatch, capsys):
    sync_state = _load_sync_state_module()
    db_path = tmp_path / "agent" / "TASK_QUEUE.json"
    stale = datetime.now(timezone.utc) - timedelta(seconds=sync_state.HEARTBEAT_TTL_SECONDS + 5)
    _write_db(
        db_path,
        [
            {
                "id": 3,
                "title": "Stale task",
                "description": "desc",
                "ref": "NONE",
                "status": "in_progress",
                "assigned_to": "autodna",
                "heartbeat_at": stale.isoformat().replace("+00:00", "Z"),
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(sync_state, "DB_FILE", db_path)

    sync_state.reserve(3, "codex")
    out = capsys.readouterr().out
    assert "Reclaimed stale Task #3 from autodna for codex" in out

    data = _load_db(db_path)
    assert data["tasks"][0]["assigned_to"] == "codex"
    assert data["tasks"][0]["heartbeat_at"].endswith("Z")


def test_status_counts_stale_tasks_as_claimable(tmp_path, monkeypatch, capsys):
    sync_state = _load_sync_state_module()
    db_path = tmp_path / "agent" / "TASK_QUEUE.json"
    now = datetime.now(timezone.utc)
    stale = now - timedelta(seconds=sync_state.HEARTBEAT_TTL_SECONDS + 5)
    _write_db(
        db_path,
        [
            {
                "id": 1,
                "title": "Fresh task",
                "description": "desc",
                "ref": "NONE",
                "status": "in_progress",
                "assigned_to": "agent-a",
                "heartbeat_at": now.isoformat().replace("+00:00", "Z"),
                "updated_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": 2,
                "title": "Stale task",
                "description": "desc",
                "ref": "NONE",
                "status": "in_progress",
                "assigned_to": "agent-b",
                "heartbeat_at": stale.isoformat().replace("+00:00", "Z"),
                "updated_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": 3,
                "title": "Pending task",
                "description": "desc",
                "ref": "NONE",
                "status": "pending",
                "assigned_to": None,
                "updated_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": 4,
                "title": "Done task",
                "description": "desc",
                "ref": "NONE",
                "status": "completed",
                "assigned_to": None,
                "updated_at": "2026-01-01T00:00:00Z",
            },
        ],
    )
    monkeypatch.setattr(sync_state, "DB_FILE", db_path)

    sync_state.status()
    out = capsys.readouterr().out

    assert "IN PROGRESS: 1" in out
    assert "STALE CLAIMABLE: 1" in out
    assert "AVAILABLE: 2" in out
