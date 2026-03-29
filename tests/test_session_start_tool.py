import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _load_session_start_module():
    module_path = Path(__file__).resolve().parents[1] / "tools" / "session_start.py"
    spec = importlib.util.spec_from_file_location("session_start_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_load_tasks_json_separates_stale_claimable(tmp_path):
    session_start = _load_session_start_module()
    queue_path = tmp_path / "TASK_QUEUE.json"
    now = datetime.now(timezone.utc)
    stale = now - timedelta(seconds=session_start.HEARTBEAT_TTL_SECONDS + 5)
    queue_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": 1,
                        "title": "Fresh task",
                        "status": "in_progress",
                        "assigned_to": "agent-a",
                        "heartbeat_at": now.isoformat().replace("+00:00", "Z"),
                    },
                    {
                        "id": 2,
                        "title": "Stale task",
                        "status": "in_progress",
                        "assigned_to": "agent-b",
                        "heartbeat_at": stale.isoformat().replace("+00:00", "Z"),
                    },
                    {
                        "id": 3,
                        "title": "Pending task",
                        "status": "pending",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    active, available, stale_tasks = session_start.load_tasks_json(queue_path)

    assert [task["id"] for task in active] == [1]
    assert [task["id"] for task in available] == [2, 3]
    assert [task["id"] for task in stale_tasks] == [2]
