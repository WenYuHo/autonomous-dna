import json

from autodna.tools import taskgen


def test_taskgen_creates_tasks_when_empty(tmp_path):
    queue_path = tmp_path / "TASK_QUEUE.json"
    artifact_path = tmp_path / "artifact.md"
    artifact_path.write_text("research content", encoding="utf-8")

    created, count = taskgen.run_taskgen(
        queue_path=queue_path,
        artifact_path=artifact_path,
        if_empty=True,
        dry_run=False,
    )

    assert created is True
    assert count == 4

    data = json.loads(queue_path.read_text(encoding="utf-8"))
    tasks = data["tasks"]
    assert len(tasks) == 4
    assert tasks[0]["status"] == "info"
    assert tasks[1]["ref"] == str(artifact_path)
    assert tasks[2]["blocked_by"] == tasks[1]["id"]
    assert tasks[3]["blocked_by"] == tasks[2]["id"]


def test_taskgen_skips_when_actionable(tmp_path):
    queue_path = tmp_path / "TASK_QUEUE.json"
    seed = {
        "tasks": [
            {
                "id": 1,
                "title": "[IMPROVE] Existing task",
                "description": "Do something",
                "ref": "NONE",
                "status": "pending",
                "assigned_to": None,
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ]
    }
    queue_path.write_text(json.dumps(seed), encoding="utf-8")

    created, count = taskgen.run_taskgen(
        queue_path=queue_path,
        artifact_path=None,
        if_empty=True,
        dry_run=False,
    )

    assert created is False
    assert count == 0
    data = json.loads(queue_path.read_text(encoding="utf-8"))
    assert len(data["tasks"]) == 1
