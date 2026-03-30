import io
import importlib.util
import json
import queue
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest


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

    leftover_task = {"id": 11, "title": self_improve.LEFTOVER_TASK_TITLE, "status": "pending", "notes": ""}
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
        leftover_task["status"] = "completed"
        leftover_task["notes"] = "leftover follow-up completed"
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
    monkeypatch.setattr(self_improve, "_capture_dogfood_report", lambda label, notes="": Path("agent/dogfood_reports/test.md"))
    monkeypatch.setattr(
        self_improve,
        "_run_required_tests",
        lambda: {"kind": "tests", "status": "pass", "command": "python -m pytest -q", "exit_code": 0},
    )
    monkeypatch.setattr(
        self_improve,
        "_run_evaluation_gate",
        lambda task_id, baseline_report, notes="": {"kind": "evaluation", "status": "pass", "gates": ["backlog_delta<=0"]},
    )
    monkeypatch.setattr(self_improve, "run_agent", fake_run_agent)
    monkeypatch.setattr(self_improve.outcome_api, "record_outcome", fake_record_outcome)

    with patch.object(self_improve.sys, "argv", ["self_improve.py", "--skip-git-preflight"]):
        self_improve.main()

    assert state["select_calls"] >= 2
    assert state["claimed"] == 1
    assert state["ran"] == 1
    assert state["recorded"] == 1


def test_should_refresh_research_uses_stale_policy(monkeypatch):
    self_improve = _load_self_improve_module()
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("AUTODNA_SELF_IMPROVE_RESEARCH_POLICY", "stale")
    monkeypatch.setenv("AUTODNA_SELF_IMPROVE_RESEARCH_MAX_AGE_SECONDS", "3600")

    monkeypatch.setattr(self_improve, "_latest_research_artifact_time", lambda: now - timedelta(hours=2))
    assert self_improve._should_refresh_research(queue_empty=False) is True

    monkeypatch.setattr(self_improve, "_latest_research_artifact_time", lambda: now - timedelta(minutes=5))
    assert self_improve._should_refresh_research(queue_empty=False) is False


def test_maybe_refresh_research_runs_proactively_for_always_policy(monkeypatch):
    self_improve = _load_self_improve_module()
    monkeypatch.setenv("AUTODNA_SELF_IMPROVE_RESEARCH_POLICY", "always")
    calls = {"count": 0}

    def fake_refresh(topic=None):
        calls["count"] += 1
        return True

    monkeypatch.setattr(self_improve, "_refresh_research", fake_refresh)

    assert self_improve._maybe_refresh_research(queue_empty=False) is True
    assert calls["count"] == 1


def test_main_refreshes_research_before_selecting_task_for_always_policy(monkeypatch):
    self_improve = _load_self_improve_module()
    monkeypatch.setenv("AUTODNA_SELF_IMPROVE_AUTO_BOOTSTRAP", "0")
    monkeypatch.setenv("AUTODNA_SELF_IMPROVE_RESEARCH_POLICY", "always")
    calls = {"count": 0}

    monkeypatch.setattr(
        self_improve,
        "_refresh_research",
        lambda topic=None: calls.__setitem__("count", calls["count"] + 1) or True,
    )
    monkeypatch.setattr(self_improve, "_select_actionable_task", lambda _agent: None)
    monkeypatch.setattr(self_improve, "_active_agents", lambda _tasks: set())
    monkeypatch.setattr(self_improve, "_ensure_leftover_followup_task", lambda: {"created": False, "task_id": None, "file_count": 0})

    with patch.object(self_improve.sys, "argv", ["self_improve.py", "--skip-git-preflight", "--dry-run"]):
        self_improve.main()

    assert calls["count"] == 1


def test_run_agent_rejects_clean_exit_without_completed_queue_task(monkeypatch):
    self_improve = _load_self_improve_module()
    task = {"id": 21, "title": "Pending task", "status": "pending", "notes": ""}

    class FakeProcess:
        def __init__(self):
            self.stdout = io.StringIO("")
            self.returncode = 0

        def poll(self):
            return 0

        def terminate(self):
            return None

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    output_queue: queue.Queue = queue.Queue()
    output_queue.put(None)

    monkeypatch.setattr(self_improve.engine_start, "build_agent_mission", lambda agent_name, task_id: "mission")
    monkeypatch.setattr(self_improve, "_load_tasks", lambda: [task])
    monkeypatch.setattr(self_improve.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(self_improve, "_start_output_reader", lambda _process: output_queue)

    status, note = self_improve.run_agent(task, timeout_seconds=5, agent_name="autodna")

    assert status == "error"
    assert "without marking the task completed" in note


def test_run_evaluation_gate_uses_dogfood_compare_flow(tmp_path, monkeypatch):
    self_improve = _load_self_improve_module()
    baseline_path = tmp_path / "baseline.md"
    after_path = tmp_path / "after.md"
    out_dir = tmp_path / "reports"
    baseline_path.write_text(
        "# Dogfood Report\n"
        "- Timestamp: 2026-03-15T00:00:00Z\n"
        "- Label: baseline\n"
        "- Repo: /tmp/repo\n"
        "- Notes: baseline\n"
        "\n"
        "## Signals\n"
        "- Memory facts: 10\n"
        "- Task counts: in_progress=1, backlog=2, done=3\n"
        "- Task queue last_sync: 2026-03-15T01:00:00Z\n",
        encoding="utf-8",
    )
    after_path.write_text(
        "# Dogfood Report\n"
        "- Timestamp: 2026-03-15T00:10:00Z\n"
        "- Label: after\n"
        "- Repo: /tmp/repo\n"
        "- Notes: after\n"
        "\n"
        "## Signals\n"
        "- Memory facts: 10\n"
        "- Task counts: in_progress=0, backlog=1, done=4\n"
        "- Task queue last_sync: 2026-03-15T01:10:00Z\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(self_improve, "DOGFOOD_OUT_DIR", out_dir)
    monkeypatch.setattr(self_improve, "_capture_dogfood_report", lambda label, notes="": after_path)
    monkeypatch.delenv("AUTODNA_SELF_IMPROVE_NO_DEFAULT_GATES", raising=False)
    monkeypatch.delenv("AUTODNA_SELF_IMPROVE_GATES", raising=False)

    receipt = self_improve._run_evaluation_gate(17, baseline_path, notes="comparison")

    assert receipt["status"] == "pass"
    assert receipt["deltas"]["backlog_delta"] == -1
    assert Path(receipt["compare_report"]).exists()


def test_finalize_done_status_ignores_stale_success_receipts(tmp_path, monkeypatch):
    self_improve = _load_self_improve_module()
    queue_path = tmp_path / "TASK_QUEUE.json"
    stale_notes = "\n\n".join(
        [
            "prior human note",
            self_improve._receipt_line("tests", status="pass", command="old tests"),
            self_improve._receipt_line("evaluation", status="pass", gates=["backlog_delta<=0"]),
        ]
    )
    queue_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": 21,
                        "title": "Retry with stale receipts",
                        "status": "completed",
                        "notes": stale_notes,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(self_improve, "TASK_QUEUE_FILE", queue_path)
    monkeypatch.setattr(
        self_improve,
        "_run_required_tests",
        lambda: {"kind": "tests", "status": "fail", "command": "python -m pytest -q", "exit_code": 1},
    )
    monkeypatch.setattr(
        self_improve,
        "_run_evaluation_gate",
        lambda task_id, baseline_report, notes="": {"kind": "evaluation", "status": "pass", "gates": ["backlog_delta<=0"]},
    )

    status, notes = self_improve._finalize_done_status(21, tmp_path / "baseline.md", None)

    assert status == "error"
    assert "prior human note" in notes
    assert "required tests failed" in notes
    assert self_improve._has_success_receipt(notes, "tests") is False
    assert self_improve._has_success_receipt(notes, "evaluation") is True


def test_run_agent_rejects_clean_exit_without_queue_completion(monkeypatch):
    self_improve = _load_self_improve_module()

    class FakeProcess:
        def __init__(self):
            self.stdout = None
            self.returncode = 0

        def poll(self):
            return 0

        def terminate(self):
            return None

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    monkeypatch.setattr(self_improve.engine_start, "build_agent_mission", lambda agent_name, task_id: "mission")
    monkeypatch.setattr(self_improve.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(
        self_improve,
        "_load_tasks",
        lambda: [{"id": 22, "title": "Unfinished task", "status": "in_progress", "notes": "still running"}],
    )

    status, note = self_improve.run_agent({"id": 22, "title": "Unfinished task"}, timeout_seconds=1, agent_name="autodna")

    assert status == "error"
    assert "without marking the task completed" in note


def test_main_accepts_done_only_with_success_receipts(tmp_path, monkeypatch):
    self_improve = _load_self_improve_module()
    queue_path = tmp_path / "TASK_QUEUE.json"
    queue_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": 7,
                        "title": "Receipt-backed improvement",
                        "description": "Verify controller gating.",
                        "status": "pending",
                        "assigned_to": None,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    baseline_report = tmp_path / "baseline.md"
    baseline_report.write_text("# Dogfood Report\n", encoding="utf-8")
    recorded = {}

    monkeypatch.setattr(self_improve, "TASK_QUEUE_FILE", queue_path)
    monkeypatch.setenv("AUTODNA_SELF_IMPROVE_AUTO_BOOTSTRAP", "0")
    monkeypatch.setattr(self_improve, "_active_agents", lambda _tasks: set())
    monkeypatch.setattr(self_improve, "_maybe_refresh_research", lambda **_kwargs: False)
    monkeypatch.setattr(self_improve, "_select_actionable_task", lambda _agent: self_improve._load_tasks()[0])
    monkeypatch.setattr(self_improve, "_capture_dogfood_report", lambda label, notes="": baseline_report)
    monkeypatch.setattr(
        self_improve,
        "_run_required_tests",
        lambda: {"kind": "tests", "status": "pass", "command": "python -m pytest -q", "exit_code": 0},
    )
    monkeypatch.setattr(
        self_improve,
        "_run_evaluation_gate",
        lambda task_id, baseline_report, notes="": {
            "kind": "evaluation",
            "status": "pass",
            "gates": ["backlog_delta<=0"],
            "baseline_report": str(baseline_report),
        },
    )
    monkeypatch.setattr(self_improve.issue_detector, "detect_recurring_issues", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(self_improve.issue_detector, "auto_create_fix_tasks", lambda *_args, **_kwargs: None)

    def fake_record_outcome(task_id, status, notes, agent_name, outcomes_dir):
        recorded.update(
            {
                "task_id": task_id,
                "status": status,
                "notes": notes,
                "agent_name": agent_name,
                "outcomes_dir": outcomes_dir,
            }
        )

    def fake_run_agent(task, timeout_seconds, agent_name):
        assert task["id"] == 7
        assert timeout_seconds > 0
        self_improve._update_task_state(task["id"], "completed", "agent completed task", assigned_to=agent_name)
        return "done", None

    monkeypatch.setattr(self_improve.outcome_api, "record_outcome", fake_record_outcome)
    monkeypatch.setattr(self_improve, "run_agent", fake_run_agent)

    with patch.object(self_improve.sys, "argv", ["self_improve.py", "--skip-git-preflight"]):
        self_improve.main()

    task = self_improve._load_tasks()[0]
    assert task["status"] == "completed"
    assert task["assigned_to"] is None
    assert self_improve._has_success_receipt(task.get("notes"), "tests")
    assert self_improve._has_success_receipt(task.get("notes"), "evaluation")
    assert recorded["status"] == "done"
    assert self_improve._has_success_receipt(recorded["notes"], "tests")
    assert self_improve._has_success_receipt(recorded["notes"], "evaluation")


def test_main_rejects_done_when_required_tests_fail(tmp_path, monkeypatch):
    self_improve = _load_self_improve_module()
    queue_path = tmp_path / "TASK_QUEUE.json"
    queue_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": 8,
                        "title": "Failing verification",
                        "description": "Require controller rejection.",
                        "status": "pending",
                        "assigned_to": None,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    baseline_report = tmp_path / "baseline.md"
    baseline_report.write_text("# Dogfood Report\n", encoding="utf-8")
    recorded = {}

    monkeypatch.setattr(self_improve, "TASK_QUEUE_FILE", queue_path)
    monkeypatch.setenv("AUTODNA_SELF_IMPROVE_AUTO_BOOTSTRAP", "0")
    monkeypatch.setattr(self_improve, "_active_agents", lambda _tasks: set())
    monkeypatch.setattr(self_improve, "_maybe_refresh_research", lambda **_kwargs: False)
    monkeypatch.setattr(self_improve, "_select_actionable_task", lambda _agent: self_improve._load_tasks()[0])
    monkeypatch.setattr(self_improve, "_capture_dogfood_report", lambda label, notes="": baseline_report)
    monkeypatch.setattr(
        self_improve,
        "_run_required_tests",
        lambda: {"kind": "tests", "status": "fail", "command": "python -m pytest -q", "exit_code": 1},
    )
    monkeypatch.setattr(
        self_improve,
        "_run_evaluation_gate",
        lambda task_id, baseline_report, notes="": {
            "kind": "evaluation",
            "status": "pass",
            "gates": ["backlog_delta<=0"],
        },
    )
    monkeypatch.setattr(self_improve.issue_detector, "detect_recurring_issues", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(self_improve.issue_detector, "auto_create_fix_tasks", lambda *_args, **_kwargs: None)

    def fake_record_outcome(task_id, status, notes, agent_name, outcomes_dir):
        recorded.update({"task_id": task_id, "status": status, "notes": notes, "agent_name": agent_name})

    def fake_run_agent(task, timeout_seconds, agent_name):
        self_improve._update_task_state(task["id"], "completed", "agent completed task", assigned_to=agent_name)
        return "done", None

    monkeypatch.setattr(self_improve.outcome_api, "record_outcome", fake_record_outcome)
    monkeypatch.setattr(self_improve, "run_agent", fake_run_agent)

    with patch.object(self_improve.sys, "argv", ["self_improve.py", "--skip-git-preflight"]):
        with pytest.raises(SystemExit) as excinfo:
            self_improve.main()

    assert excinfo.value.code == 1
    task = self_improve._load_tasks()[0]
    assert task["status"] == "error"
    assert "required tests failed" in task.get("notes", "")
    assert self_improve._has_success_receipt(task.get("notes"), "tests") is False
    assert self_improve._has_success_receipt(task.get("notes"), "evaluation") is True
    assert recorded["status"] == "error"


def test_main_rejects_done_when_evaluation_gate_fails(tmp_path, monkeypatch):
    self_improve = _load_self_improve_module()
    queue_path = tmp_path / "TASK_QUEUE.json"
    queue_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": 9,
                        "title": "Evaluation-gated improvement",
                        "description": "Require dogfood pass.",
                        "status": "pending",
                        "assigned_to": None,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    baseline_report = tmp_path / "baseline.md"
    baseline_report.write_text("# Dogfood Report\n", encoding="utf-8")
    recorded = {}

    monkeypatch.setattr(self_improve, "TASK_QUEUE_FILE", queue_path)
    monkeypatch.setenv("AUTODNA_SELF_IMPROVE_AUTO_BOOTSTRAP", "0")
    monkeypatch.setattr(self_improve, "_active_agents", lambda _tasks: set())
    monkeypatch.setattr(self_improve, "_maybe_refresh_research", lambda **_kwargs: False)
    monkeypatch.setattr(self_improve, "_select_actionable_task", lambda _agent: self_improve._load_tasks()[0])
    monkeypatch.setattr(self_improve, "_capture_dogfood_report", lambda label, notes="": baseline_report)
    monkeypatch.setattr(
        self_improve,
        "_run_required_tests",
        lambda: {"kind": "tests", "status": "pass", "command": "python -m pytest -q", "exit_code": 0},
    )
    monkeypatch.setattr(
        self_improve,
        "_run_evaluation_gate",
        lambda task_id, baseline_report, notes="": {
            "kind": "evaluation",
            "status": "fail",
            "gates": ["backlog_delta<=0"],
            "failures": ["backlog_delta<=0 (value=1)"],
        },
    )
    monkeypatch.setattr(self_improve.issue_detector, "detect_recurring_issues", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(self_improve.issue_detector, "auto_create_fix_tasks", lambda *_args, **_kwargs: None)

    def fake_record_outcome(task_id, status, notes, agent_name, outcomes_dir):
        recorded.update({"task_id": task_id, "status": status, "notes": notes, "agent_name": agent_name})

    def fake_run_agent(task, timeout_seconds, agent_name):
        self_improve._update_task_state(task["id"], "completed", "agent completed task", assigned_to=agent_name)
        return "done", None

    monkeypatch.setattr(self_improve.outcome_api, "record_outcome", fake_record_outcome)
    monkeypatch.setattr(self_improve, "run_agent", fake_run_agent)

    with patch.object(self_improve.sys, "argv", ["self_improve.py", "--skip-git-preflight"]):
        with pytest.raises(SystemExit) as excinfo:
            self_improve.main()

    assert excinfo.value.code == 1
    task = self_improve._load_tasks()[0]
    assert task["status"] == "error"
    assert "dogfood evaluation gate failed" in task.get("notes", "")
    assert self_improve._has_success_receipt(task.get("notes"), "tests") is True
    assert self_improve._has_success_receipt(task.get("notes"), "evaluation") is False
    assert recorded["status"] == "error"
