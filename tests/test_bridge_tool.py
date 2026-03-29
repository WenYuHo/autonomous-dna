import json

import bridge


def test_ensure_state_files_bootstraps_json_queue(tmp_path):
    created = bridge.ensure_state_files(tmp_path)

    assert "agent/TASK_QUEUE.json" in created

    queue_path = tmp_path / "agent" / "TASK_QUEUE.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))

    assert "tasks" in queue
    assert isinstance(queue["tasks"], list)
    assert len(queue["tasks"]) == 1

    task = queue["tasks"][0]
    assert task["id"] == 1
    assert task["title"] == "INITIAL_SETUP"
    assert task["status"] == "pending"
    assert task["assigned_to"] is None
    assert task["ref"] == "NONE"
    assert task["updated_at"].endswith("Z")


def test_ensure_state_files_keeps_existing_json_queue(tmp_path):
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    queue_path = agent_dir / "TASK_QUEUE.json"
    original = {
        "tasks": [
            {
                "id": 42,
                "title": "EXISTING",
                "description": "keep me",
                "ref": "NONE",
                "status": "pending",
                "assigned_to": None,
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ]
    }
    queue_path.write_text(json.dumps(original, indent=2), encoding="utf-8")

    created = bridge.ensure_state_files(tmp_path)

    assert "agent/TASK_QUEUE.json" not in created
    assert json.loads(queue_path.read_text(encoding="utf-8")) == original
