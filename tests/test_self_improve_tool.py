import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


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
        "assigned_to": "agent-a",
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


def test_active_agents_uses_heartbeat():
    self_improve = _load_self_improve_module()
    now = datetime.now(timezone.utc)
    stale = now - timedelta(seconds=self_improve.HEARTBEAT_TTL_SECONDS + 5)
    tasks = [
        {
            "status": "in_progress",
            "assigned_to": "agent-a",
            "heartbeat_at": now.isoformat().replace("+00:00", "Z"),
        },
        {
            "status": "in_progress",
            "assigned_to": "agent-b",
            "heartbeat_at": stale.isoformat().replace("+00:00", "Z"),
        },
        {
            "status": "pending",
            "assigned_to": "agent-c",
            "heartbeat_at": now.isoformat().replace("+00:00", "Z"),
        },
    ]

    active = self_improve._active_agents(tasks)

    assert active == {"agent-a"}


def test_git_preflight_blocks_when_git_state_is_not_clean():
    self_improve = _load_self_improve_module()

    with patch.object(
        self_improve.git_ops,
        "inspect_git_state",
        return_value={
            "ok": False,
            "issues": [
                "Working tree has uncommitted or untracked changes.",
                "Branch is ahead of upstream by 2 commit(s); ship pending commits first.",
            ],
        },
    ):
        ok, note = self_improve._git_preflight(fetch=True)

    assert ok is False
    assert "uncommitted or untracked changes" in note
    assert "ahead of upstream by 2 commit(s)" in note


def test_ensure_leftover_followup_task_creates_task_once(tmp_path, monkeypatch):
    self_improve = _load_self_improve_module()
    queue_path = tmp_path / "TASK_QUEUE.json"
    queue_path.write_text(json.dumps({"tasks": []}), encoding="utf-8")
    monkeypatch.setattr(self_improve, "TASK_QUEUE_FILE", queue_path)
    monkeypatch.setattr(self_improve, "_collect_leftover_files", lambda: ["tools/git_ops.py", "tests/test_git_ops.py"])

    def fake_add_task(title, description, ref="NONE"):
        db = self_improve._load_queue_data()
        db["tasks"].append(
            {
                "id": 9,
                "title": title,
                "description": description,
                "ref": ref,
                "status": "pending",
            }
        )
        self_improve._save_queue_data(db)

    monkeypatch.setattr(self_improve.task_api, "add_task", fake_add_task)
    result = self_improve._ensure_leftover_followup_task()

    assert result == {"created": True, "task_id": 9, "file_count": 2}
    db = json.loads(queue_path.read_text(encoding="utf-8"))
    assert len(db["tasks"]) == 1
    assert db["tasks"][0]["title"] == self_improve.LEFTOVER_TASK_TITLE


def test_ensure_leftover_followup_task_deduplicates_existing(tmp_path, monkeypatch):
    self_improve = _load_self_improve_module()
    files = ["bridge.py", "autodna/tools/research.py"]
    signature = self_improve._leftover_signature(files)
    queue_path = tmp_path / "TASK_QUEUE.json"
    queue_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": 3,
                        "title": self_improve.LEFTOVER_TASK_TITLE,
                        "description": f"pending cleanup {self_improve.LEFTOVER_SIGNATURE_KEY}{signature}",
                        "status": "pending",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(self_improve, "TASK_QUEUE_FILE", queue_path)
    monkeypatch.setattr(self_improve, "_collect_leftover_files", lambda: files)
    monkeypatch.setattr(
        self_improve.task_api,
        "add_task",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not add duplicate leftover task")),
    )

    result = self_improve._ensure_leftover_followup_task()

    assert result == {"created": False, "task_id": 3, "file_count": 2}


def test_main_creates_leftover_followup_when_no_actionable_task(monkeypatch):
    self_improve = _load_self_improve_module()
    monkeypatch.setenv("AUTODNA_SELF_IMPROVE_AUTO_BOOTSTRAP", "0")
    called = {"count": 0}

    monkeypatch.setattr(self_improve, "_select_actionable_task", lambda _agent: None)
    monkeypatch.setattr(self_improve, "_active_agents", lambda _tasks: set())
    monkeypatch.setattr(
        self_improve,
        "_ensure_leftover_followup_task",
        lambda: called.__setitem__("count", called["count"] + 1) or {"created": True, "task_id": 11, "file_count": 2},
    )

    with patch.object(self_improve.sys, "argv", ["self_improve.py", "--skip-git-preflight"]):
        self_improve.main()

    assert called["count"] == 1


def test_main_runs_newly_created_leftover_followup_in_same_invocation(monkeypatch):
    self_improve = _load_self_improve_module()
    monkeypatch.setenv("AUTODNA_SELF_IMPROVE_AUTO_BOOTSTRAP", "0")

    leftover_task = {"id": 11, "title": self_improve.LEFTOVER_TASK_TITLE, "status": "pending"}
    state = {"select_calls": 0, "claimed": 0, "ran": 0, "recorded": 0}

    def fake_select(_agent_name):
        state["select_calls"] += 1
        if state["select_calls"] == 1:
            return None
        return leftover_task

    def fake_claim(task_id, _agent_name):
        assert task_id == 11
        state["claimed"] += 1
        return True

    def fake_run_agent(task, timeout_seconds, agent_name):
        assert task["id"] == 11
        assert timeout_seconds > 0
        assert agent_name
        state["ran"] += 1
        return "done", None

    def fake_record_outcome(*_args, **_kwargs):
        state["recorded"] += 1

    monkeypatch.setattr(self_improve, "_select_actionable_task", fake_select)
    monkeypatch.setattr(self_improve, "_active_agents", lambda _tasks: set())
    monkeypatch.setattr(
        self_improve,
        "_ensure_leftover_followup_task",
        lambda: {"created": True, "task_id": 11, "file_count": 2},
    )
    monkeypatch.setattr(self_improve, "_claim_task_for_agent", fake_claim)
    monkeypatch.setattr(self_improve, "_load_tasks", lambda: [leftover_task])
    monkeypatch.setattr(self_improve, "run_agent", fake_run_agent)
    monkeypatch.setattr(self_improve.outcome_api, "record_outcome", fake_record_outcome)

    with patch.object(self_improve.sys, "argv", ["self_improve.py", "--skip-git-preflight"]):
        self_improve.main()

    assert state["select_calls"] >= 2
    assert state["claimed"] == 1
    assert state["ran"] == 1
    assert state["recorded"] == 1
