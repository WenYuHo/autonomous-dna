import json
from datetime import datetime, timezone, timedelta

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

    # Verify Recipe and Acceptance Criteria are present in descriptions
    for i in [1, 2, 3]:
        desc = tasks[i].get("description", "")
        assert "Recipe:" in desc
        assert "Acceptance Criteria:" in desc


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


def test_taskgen_skips_when_artifact_reused(tmp_path):
    queue_path = tmp_path / "TASK_QUEUE.json"
    artifact_path = tmp_path / "artifact.md"
    artifact_path.write_text("research content", encoding="utf-8")
    seed = {
        "tasks": [
            {
                "id": 10,
                "title": "CYCLE 9 — AUTOGEN: Research Synthesis",
                "description": "Auto cycle",
                "ref": str(artifact_path),
                "status": "info",
                "assigned_to": None,
                "updated_at": "2026-01-01T00:00:00Z",
                "cycle": 9,
            }
        ]
    }
    queue_path.write_text(json.dumps(seed), encoding="utf-8")

    created, count = taskgen.run_taskgen(
        queue_path=queue_path,
        artifact_path=artifact_path,
        if_empty=True,
        dry_run=False,
    )

    assert created is False
    assert count == 0
    data = json.loads(queue_path.read_text(encoding="utf-8"))
    assert len(data["tasks"]) == 1


def test_has_actionable_tasks_unblocks_completed():
    tasks = [
        {
            "id": 1,
            "title": "[RESEARCH] Completed blocker",
            "status": "completed",
        },
        {
            "id": 2,
            "title": "[IMPROVE] Unblocked task",
            "status": "pending",
            "blocked_by": 1,
        },
    ]

    assert taskgen.has_actionable_tasks(tasks) is True


def test_has_actionable_tasks_in_progress():
    tasks = [
        {
            "id": 1,
            "title": "[IMPROVE] Active work",
            "status": "in_progress",
        }
    ]

    assert taskgen.has_actionable_tasks(tasks) is True


def test_has_actionable_tasks_error_unblocked():
    tasks = [
        {
            "id": 1,
            "title": "[RESEARCH] Done blocker",
            "status": "completed",
        },
        {
            "id": 2,
            "title": "[IMPROVE] Failed task",
            "status": "error",
            "blocked_by": 1,
        },
    ]

    assert taskgen.has_actionable_tasks(tasks) is True


def test_has_actionable_tasks_is_blocked_by_pending():
    tasks = [
        {
            "id": 1,
            "title": "[RESEARCH] Pending blocker",
            "status": "pending",
        },
        {
            "id": 2,
            "title": "[IMPROVE] Blocked task",
            "status": "pending",
            "blocked_by": 1,
        },
    ]

    # Task 1 is actionable. Task 2 is blocked.
    assert taskgen.has_actionable_tasks(tasks) is True


def test_has_actionable_tasks_is_blocked_by_error():
    tasks = [
        {
            "id": 1,
            "title": "[RESEARCH] Error blocker",
            "status": "error",
        },
        {
            "id": 2,
            "title": "[IMPROVE] Blocked task",
            "status": "pending",
            "blocked_by": 1,
        },
    ]

    # Task 1 is actionable (retry candidate). Task 2 is blocked.
    assert taskgen.has_actionable_tasks(tasks) is True


def test_has_actionable_tasks_false_when_all_blocked_by_active_heartbeat():
    now = datetime.now(timezone.utc)
    tasks = [
        {
            "id": 1,
            "title": "[RESEARCH] Active blocker",
            "status": "in_progress",
            "assigned_to": "agent-a",
            "heartbeat_at": now.isoformat().replace("+00:00", "Z"),
        },
        {
            "id": 2,
            "title": "[IMPROVE] Blocked task",
            "status": "pending",
            "blocked_by": 1,
        },
    ]

    # Task 1 is already in_progress and heartbeat is fresh.
    assert taskgen.has_actionable_tasks(tasks) is True


def test_has_actionable_tasks_unblocks_when_heartbeat_stale():
    old = datetime.now(timezone.utc) - timedelta(seconds=taskgen.HEARTBEAT_TTL_SECONDS + 5)
    tasks = [
        {
            "id": 1,
            "title": "[RESEARCH] Stale blocker",
            "status": "in_progress",
            "assigned_to": "agent-a",
            "heartbeat_at": old.isoformat().replace("+00:00", "Z"),
        },
        {
            "id": 2,
            "title": "[IMPROVE] Blocked task",
            "status": "pending",
            "blocked_by": 1,
        },
    ]

    assert taskgen.has_actionable_tasks(tasks) is True
