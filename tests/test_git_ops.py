import subprocess

import pytest

from tools import git_ops


def _cp(cmd, rc=0, out="", err=""):
    return subprocess.CompletedProcess(cmd, rc, out, err)


def test_resolve_base_branch_prefers_env(monkeypatch):
    monkeypatch.setenv("AUTODNA_GIT_BASE_BRANCH", "dev")
    monkeypatch.setattr(git_ops, "_branch_exists", lambda name: name == "dev")
    assert git_ops.resolve_base_branch() == "dev"


def test_branch_name_uses_prefix_and_description(monkeypatch):
    monkeypatch.setenv("AUTODNA_GIT_BRANCH_PREFIX", "chore/")
    assert git_ops.branch_name("TASK_5", "Fix Queue flow") == "chore/task_5-fix-queue-flow"


def test_run_tests_skips_when_disabled(monkeypatch):
    monkeypatch.setenv("AUTODNA_GIT_TEST_CMD", "")
    called = {"count": 0}

    def fake_run(cmd, check=False):
        called["count"] += 1
        return _cp(cmd)

    monkeypatch.setattr(git_ops, "run", fake_run)
    git_ops.run_tests()
    assert called["count"] == 0


def test_run_tests_exits_on_failure(monkeypatch):
    monkeypatch.setenv("AUTODNA_GIT_TEST_CMD", "python -m pytest tests/")
    monkeypatch.setattr(git_ops, "run", lambda cmd, check=False: _cp(cmd, rc=1, out="fail", err="fail"))
    with pytest.raises(SystemExit):
        git_ops.run_tests()


def test_parse_branch_status_extracts_branch_sync_state():
    output = "\n".join(
        [
            "# branch.oid abcdef",
            "# branch.head dev",
            "# branch.upstream origin/dev",
            "# branch.ab +2 -3",
            "? new_file.py",
        ]
    )

    state = git_ops._parse_branch_status(output)

    assert state["branch"] == "dev"
    assert state["upstream"] == "origin/dev"
    assert state["ahead"] == 2
    assert state["behind"] == 3
    assert state["dirty"] is True


def test_inspect_git_state_reports_dirty_and_ahead(monkeypatch):
    statuses = iter(
        [
            _cp(
                ["git", "status"],
                out="\n".join(
                    [
                        "# branch.oid abcdef",
                        "# branch.head dev",
                        "# branch.upstream origin/dev",
                        "# branch.ab +4 -0",
                        "1 .M N... 100644 100644 100644 file.py file.py",
                    ]
                ),
            ),
            _cp(["git", "fetch"]),
            _cp(
                ["git", "status"],
                out="\n".join(
                    [
                        "# branch.oid abcdef",
                        "# branch.head dev",
                        "# branch.upstream origin/dev",
                        "# branch.ab +4 -0",
                        "1 .M N... 100644 100644 100644 file.py file.py",
                    ]
                ),
            ),
        ]
    )

    monkeypatch.setattr(git_ops.os.path, "exists", lambda path: path == ".git")
    monkeypatch.setattr(git_ops, "run", lambda args, check=False: next(statuses))

    state = git_ops.inspect_git_state(fetch=True)

    assert state["ok"] is False
    assert any("uncommitted or untracked changes" in issue for issue in state["issues"])
    assert any("ahead of upstream by 4 commit(s)" in issue for issue in state["issues"])


def test_inspect_git_state_reports_missing_upstream(monkeypatch):
    status = _cp(
        ["git", "status"],
        out="\n".join(
            [
                "# branch.oid abcdef",
                "# branch.head dev",
            ]
        ),
    )

    monkeypatch.setattr(git_ops.os.path, "exists", lambda path: path == ".git")
    monkeypatch.setattr(git_ops, "run", lambda args, check=False: status)

    state = git_ops.inspect_git_state(fetch=False)

    assert state["ok"] is False
    assert "Current branch has no upstream tracking branch." in state["issues"]


def test_inspect_git_state_allows_dirty_when_explicit(monkeypatch):
    status = _cp(
        ["git", "status"],
        out="\n".join(
            [
                "# branch.oid abcdef",
                "# branch.head dev",
                "1 .M N... 100644 100644 100644 file.py file.py",
            ]
        ),
    )

    monkeypatch.setattr(git_ops.os.path, "exists", lambda path: path == ".git")
    monkeypatch.setattr(git_ops, "run", lambda args, check=False: status)

    state = git_ops.inspect_git_state(fetch=False, allow_dirty=True)

    assert state["ok"] is True
    assert state["dirty"] is True
    assert state["issues"] == []


def test_rebase_with_retry_resolves_conflicts_by_policy(monkeypatch):
    calls = []
    rebases = iter([_cp(["git", "rebase"], rc=1), _cp(["git", "rebase", "--continue"])])

    def fake_run(cmd, check=False):
        calls.append(cmd)
        if cmd[:2] == ["git", "rebase"] and len(cmd) == 3:
            return next(rebases)
        if cmd == ["git", "rebase", "--continue"]:
            return _cp(cmd)
        return _cp(cmd)

    monkeypatch.setattr(git_ops, "run", fake_run)
    monkeypatch.setattr(git_ops, "_list_conflict_files", lambda: ["poetry.lock", "src/app.py"])
    logs = []
    monkeypatch.setattr(git_ops, "_log_conflict", lambda tid, path, resolution: logs.append((tid, path, resolution)))

    ok = git_ops._rebase_with_retry("TASK_5", "dev", max_attempts=2)

    assert ok is True
    assert ["git", "checkout", "--ours", "--", "poetry.lock"] in calls
    assert ["git", "checkout", "--theirs", "--", "src/app.py"] in calls
    assert ("TASK_5", "poetry.lock", "base") in logs
    assert ("TASK_5", "src/app.py", "task") in logs


def test_rebase_resolution_maps_policy_to_rebase_checkout_side():
    assert git_ops._resolution_for_conflict("src/app.py") == "task"
    assert git_ops._checkout_side_for_rebase("task") == "theirs"

    assert git_ops._resolution_for_conflict("poetry.lock") == "base"
    assert git_ops._checkout_side_for_rebase("base") == "ours"


def test_rebase_with_retry_aborts_on_scaffold_conflict(monkeypatch):
    calls = []

    def fake_run(cmd, check=False):
        calls.append(cmd)
        if cmd[:2] == ["git", "rebase"] and len(cmd) == 3:
            return _cp(cmd, rc=1)
        return _cp(cmd)

    monkeypatch.setattr(git_ops, "run", fake_run)
    monkeypatch.setattr(git_ops, "_list_conflict_files", lambda: ["AGENTS.md"])

    ok = git_ops._rebase_with_retry("TASK_5", "dev", max_attempts=1)

    assert ok is False
    assert ["git", "rebase", "--abort"] in calls


def test_git_push_rebases_and_force_pushes(monkeypatch):
    commands = []
    monkeypatch.setattr(git_ops, "run_tests", lambda: None)
    monkeypatch.setattr(git_ops, "_current_branch", lambda: "feat/task_5")
    monkeypatch.setattr(git_ops, "resolve_base_branch", lambda: "dev")
    monkeypatch.setattr(git_ops, "_rebase_with_retry", lambda tid, base: True)

    def fake_run(cmd, check=False):
        commands.append(cmd)
        if cmd == ["git", "diff", "--cached", "--quiet"]:
            return _cp(cmd, rc=1)
        return _cp(cmd)

    monkeypatch.setattr(git_ops, "run", fake_run)

    ok = git_ops.git_push("TASK_5", "update queue")

    assert ok is True
    assert ["git", "fetch", "origin"] in commands
    assert ["git", "push", "--force-with-lease", "origin", "feat/task_5"] in commands


def test_git_pr_rebases_when_behind(monkeypatch):
    commands = []
    monkeypatch.setattr(git_ops, "_gh_available", lambda: True)
    monkeypatch.setattr(git_ops, "_current_branch", lambda: "feat/task_5")
    monkeypatch.setattr(git_ops, "resolve_base_branch", lambda: "dev")
    monkeypatch.setattr(git_ops, "_find_open_pr_for_head", lambda head: None)
    monkeypatch.setattr(git_ops, "_rebase_with_retry", lambda tid, base, max_attempts=3: True)
    monkeypatch.setattr(git_ops, "_count_commits", lambda expr: 2 if expr == "feat/task_5..origin/dev" else 0)
    monkeypatch.setattr(git_ops, "run_cmd", lambda cmd: "https://example/pr/5")

    def fake_run(cmd, check=False):
        commands.append(cmd)
        return _cp(cmd)

    monkeypatch.setattr(git_ops, "run", fake_run)

    pr = git_ops.git_pr("TASK_5", body="")

    assert pr == "https://example/pr/5"
    assert ["git", "push", "--force-with-lease", "origin", "feat/task_5"] in commands


def test_git_full_runs_end_to_end(monkeypatch):
    calls = []
    monkeypatch.setattr(git_ops, "git_init", lambda tid, msg="": calls.append(("init", tid, msg)) or True)
    monkeypatch.setattr(git_ops, "git_push", lambda tid, msg: calls.append(("push", tid, msg)) or True)
    monkeypatch.setattr(git_ops, "git_pr", lambda tid, body="": calls.append(("pr", tid, body)) or "https://example/pr/9")
    monkeypatch.setattr(
        git_ops,
        "git_merge",
        lambda tid, pr_ref=None: calls.append(("merge", tid, pr_ref)) or True,
    )

    ok = git_ops.git_full("TASK_5", "update queue", body="details")

    assert ok is True
    assert calls == [
        ("init", "TASK_5", "update queue"),
        ("push", "TASK_5", "update queue"),
        ("pr", "TASK_5", "details"),
        ("merge", "TASK_5", "https://example/pr/9"),
    ]
