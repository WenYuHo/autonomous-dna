import importlib.util
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path


def _load_self_improve_module():
    module_path = Path(__file__).resolve().parents[1] / "tools" / "self_improve.py"
    spec = importlib.util.spec_from_file_location("self_improve_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_gate_env_splits_and_trims():
    self_improve = _load_self_improve_module()
    gates = self_improve.parse_gate_env("memory_facts<=100, backlog_delta<=0, ,custom>=1")

    assert gates == ["memory_facts<=100", "backlog_delta<=0", "custom>=1"]


def test_task_snapshot_from_json_counts(tmp_path):
    self_improve = _load_self_improve_module()
    queue_path = tmp_path / "TASK_QUEUE.json"
    queue_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {"status": "pending"},
                    {"status": "blocked"},
                    {"status": "error"},
                    {"status": "in_progress"},
                    {"status": "done"},
                    {"status": "completed"},
                    {"status": "info"},
                ]
            }
        ),
        encoding="utf-8",
    )

    snapshot = self_improve.task_snapshot_from_json(queue_path)

    assert snapshot["exists"] is True
    assert snapshot["counts"] == {"in_progress": 1, "backlog": 3, "done": 3}


def test_is_blocked_uses_heartbeat():
    self_improve = _load_self_improve_module()
    now = datetime.now(timezone.utc)
    blocker = {
        "id": 1,
        "title": "[RESEARCH] Active blocker",
        "status": "in_progress",
        "assigned_to": "worker-1",
        "heartbeat_at": now.isoformat().replace("+00:00", "Z"),
    }
    blocked = {
        "id": 2,
        "title": "[IMPROVE] Blocked task",
        "status": "pending",
        "blocked_by": 1,
    }
    by_id = self_improve._task_by_id([blocker, blocked])
    assert self_improve._is_blocked(blocked, by_id) is True

    stale = now - timedelta(seconds=self_improve.HEARTBEAT_TTL_SECONDS + 5)
    blocker["heartbeat_at"] = stale.isoformat().replace("+00:00", "Z")
    by_id = self_improve._task_by_id([blocker, blocked])
    assert self_improve._is_blocked(blocked, by_id) is False


def test_active_workers_uses_heartbeat():
    self_improve = _load_self_improve_module()
    now = datetime.now(timezone.utc)
    stale = now - timedelta(seconds=self_improve.HEARTBEAT_TTL_SECONDS + 5)
    tasks = [
        {
            "status": "in_progress",
            "assigned_to": "worker-1",
            "heartbeat_at": now.isoformat().replace("+00:00", "Z"),
        },
        {
            "status": "in_progress",
            "assigned_to": "worker-2",
            "heartbeat_at": stale.isoformat().replace("+00:00", "Z"),
        },
        {
            "status": "pending",
            "assigned_to": "worker-3",
            "heartbeat_at": now.isoformat().replace("+00:00", "Z"),
        },
    ]

    active = self_improve._active_workers(tasks)

    assert active == {"worker-1"}
