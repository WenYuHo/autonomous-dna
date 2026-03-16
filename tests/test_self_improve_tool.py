import json

from tools import self_improve


def test_get_retry_task_unblocked(tmp_path, monkeypatch):
    queue_path = tmp_path / "TASK_QUEUE.json"
    data = {
        "tasks": [
            {
                "id": 1,
                "title": "[IMPROVE] Retry me",
                "description": "test",
                "ref": "NONE",
                "status": "error",
                "assigned_to": None,
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ]
    }
    queue_path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(self_improve, "TASK_QUEUE_FILE", queue_path)

    task = self_improve.get_retry_task()
    assert task is not None
    assert task["id"] == 1


def test_get_retry_task_skips_blocked(tmp_path, monkeypatch):
    queue_path = tmp_path / "TASK_QUEUE.json"
    data = {
        "tasks": [
            {
                "id": 1,
                "title": "[IMPROVE] Blocker",
                "description": "blocker",
                "ref": "NONE",
                "status": "error",
                "assigned_to": None,
                "updated_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": 2,
                "title": "[IMPROVE] Blocked task",
                "description": "blocked",
                "ref": "NONE",
                "status": "error",
                "assigned_to": None,
                "updated_at": "2026-01-01T00:00:00Z",
                "blocked_by": 1,
            },
        ]
    }
    queue_path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(self_improve, "TASK_QUEUE_FILE", queue_path)

    task = self_improve.get_retry_task()
    assert task is not None
    assert task["id"] == 1


def test_select_next_task_runs_taskgen(monkeypatch):
    calls = {"count": 0}

    def fake_taskgen():
        calls["count"] += 1
        return True

    monkeypatch.setattr(self_improve, "_run_taskgen_if_available", fake_taskgen)
    monkeypatch.setattr(self_improve, "get_next_task", lambda: None)
    monkeypatch.setattr(self_improve, "get_retry_task", lambda: None)

    task = self_improve.select_next_task(always_taskgen=True)
    assert task is None
    assert calls["count"] == 1
