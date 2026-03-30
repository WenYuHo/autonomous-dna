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


def test_run_uses_utf8_decoding_for_git_commands(monkeypatch):
    calls = []

    def fake_subprocess_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return _cp(cmd, out="worktree C:/Users/tony5/OneDrive/桌面/lab")

    monkeypatch.setattr(git_ops.subprocess, "run", fake_subprocess_run)

    result = git_ops.run(["git", "worktree", "list", "--porcelain"])

    assert result.stdout == "worktree C:/Users/tony5/OneDrive/桌面/lab"
    assert calls[0][1]["encoding"] == "utf-8"
    assert calls[0][1]["errors"] == "replace"


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


def test_parse_worktree_list_porcelain_extracts_entries():
    output = "\n".join(
        [
            "worktree C:/repo",
            "HEAD abc123",
            "branch refs/heads/dev",
            "",
            "worktree C:/tmp/codex-task10",
            "HEAD def456",
            "branch refs/heads/feat/task_10",
            "prunable gitdir file points to non-existent location",
            "locked by another process",
        ]
    )

    parsed = git_ops._parse_worktree_list_porcelain(output)

    assert len(parsed) == 2
    assert parsed[0]["path"] == "C:/repo"
    assert parsed[0]["branch"] == "dev"
    assert parsed[0]["prunable"] is False
    assert parsed[1]["path"] == "C:/tmp/codex-task10"
    assert parsed[1]["branch"] == "feat/task_10"
    assert parsed[1]["prunable"] is True
    assert parsed[1]["locked"] is True


def test_list_worktrees_preserves_non_ascii_paths(monkeypatch):
    monkeypatch.setattr(
        git_ops,
        "run_cmd",
        lambda cmd: "\n".join(
            [
                "worktree C:/Users/tony5/OneDrive/桌面/Autonomous-DNA-Workspace/lab",
                "HEAD abc123",
                "branch refs/heads/feat/task_12",
            ]
        ),
    )

    worktrees = git_ops._list_worktrees()

    assert worktrees == [
        {
            "path": "C:/Users/tony5/OneDrive/桌面/Autonomous-DNA-Workspace/lab",
            "branch": "feat/task_12",
            "head": "abc123",
            "bare": False,
            "detached": False,
            "locked": False,
            "prunable": False,
        }
    ]


def test_cleanup_merged_branch_artifacts_prunes_safe_worktree_and_branches(monkeypatch):
    calls = []
    snapshots = iter(
        [
            [
                {"path": "C:/repo", "branch": "dev"},
                {"path": "C:/tmp/codex-task10", "branch": "feat/task_10"},
            ],
            [{"path": "C:/repo", "branch": "dev"}],
        ]
    )

    monkeypatch.setattr(git_ops, "_list_worktrees", lambda: next(snapshots))
    monkeypatch.setattr(git_ops, "_repo_root_path", lambda: "C:/repo")
    monkeypatch.setattr(git_ops, "_current_branch", lambda: "dev")
    monkeypatch.setattr(git_ops, "_is_branch_merged_into", lambda branch, base: True)
    monkeypatch.setattr(git_ops, "_remote_branch_exists", lambda branch: True)

    def fake_run(cmd, check=False, cwd=None):
        calls.append(cmd)
        return _cp(cmd)

    monkeypatch.setattr(git_ops, "run", fake_run)

    result = git_ops._cleanup_merged_branch_artifacts("feat/task_10", "dev")

    assert result["worktrees_removed"] == ["C:/tmp/codex-task10"]
    assert result["local_branch_deleted"] is True
    assert result["remote_branch_deleted"] is True
    assert ["git", "worktree", "remove", "C:/tmp/codex-task10"] in calls
    assert ["git", "branch", "-d", "feat/task_10"] in calls
    assert ["git", "push", "origin", "--delete", "feat/task_10"] in calls


def test_cleanup_merged_branch_artifacts_keeps_current_branch(monkeypatch):
    calls = []
    snapshots = iter(
        [
            [{"path": "C:/repo", "branch": "feat/task_10"}],
            [{"path": "C:/repo", "branch": "feat/task_10"}],
        ]
    )

    monkeypatch.setattr(git_ops, "_list_worktrees", lambda: next(snapshots))
    monkeypatch.setattr(git_ops, "_repo_root_path", lambda: "C:/repo")
    monkeypatch.setattr(git_ops, "_current_branch", lambda: "feat/task_10")
    monkeypatch.setattr(git_ops, "_is_branch_merged_into", lambda branch, base: True)
    monkeypatch.setattr(git_ops, "_remote_branch_exists", lambda branch: False)

    def fake_run(cmd, check=False, cwd=None):
        calls.append(cmd)
        return _cp(cmd)

    monkeypatch.setattr(git_ops, "run", fake_run)

    result = git_ops._cleanup_merged_branch_artifacts("feat/task_10", "dev")

    assert result["local_branch_deleted"] is False
    assert ["git", "branch", "-d", "feat/task_10"] not in calls
    assert ["git", "worktree", "remove", "C:/repo"] not in calls


def test_cleanup_merged_branch_artifacts_force_deletes_confirmed_squash_merged_branch(monkeypatch):
    calls = []
    snapshots = iter(
        [
            [{"path": "C:/repo", "branch": "dev"}],
            [{"path": "C:/repo", "branch": "dev"}],
        ]
    )

    monkeypatch.setattr(git_ops, "_list_worktrees", lambda: next(snapshots))
    monkeypatch.setattr(git_ops, "_repo_root_path", lambda: "C:/repo")
    monkeypatch.setattr(git_ops, "_current_branch", lambda: "dev")
    monkeypatch.setattr(git_ops, "_is_branch_merged_into", lambda branch, base: False)
    monkeypatch.setattr(git_ops, "_remote_branch_exists", lambda branch: False)

    def fake_run(cmd, check=False, cwd=None):
        calls.append(cmd)
        return _cp(cmd)

    monkeypatch.setattr(git_ops, "run", fake_run)

    result = git_ops._cleanup_merged_branch_artifacts("feat/task_13", "dev", confirmed_merged=True)

    assert result["local_branch_deleted"] is True
    assert ["git", "branch", "-D", "feat/task_13"] in calls
    assert ["git", "branch", "-d", "feat/task_13"] not in calls


def test_cleanup_merged_branch_artifacts_force_removes_confirmed_worktree(monkeypatch):
    calls = []
    snapshots = iter(
        [
            [
                {"path": "C:/repo", "branch": "dev"},
                {"path": "C:/tmp/codex-task14", "branch": "feat/task_14", "locked": False},
            ],
            [{"path": "C:/repo", "branch": "dev"}],
        ]
    )

    monkeypatch.setattr(git_ops, "_list_worktrees", lambda: next(snapshots))
    monkeypatch.setattr(git_ops, "_repo_root_path", lambda: "C:/repo")
    monkeypatch.setattr(git_ops, "_current_branch", lambda: "dev")
    monkeypatch.setattr(git_ops, "_is_branch_merged_into", lambda branch, base: True)
    monkeypatch.setattr(git_ops, "_remote_branch_exists", lambda branch: False)

    def fake_run(cmd, check=False, cwd=None):
        calls.append(cmd)
        if cmd == ["git", "worktree", "remove", "C:/tmp/codex-task14"]:
            return _cp(cmd, rc=1, err="contains modified or untracked files")
        return _cp(cmd)

    monkeypatch.setattr(git_ops, "run", fake_run)

    result = git_ops._cleanup_merged_branch_artifacts("feat/task_14", "dev", confirmed_merged=True)

    assert result["worktrees_removed"] == ["C:/tmp/codex-task14"]
    assert ["git", "worktree", "remove", "C:/tmp/codex-task14"] in calls
    assert ["git", "worktree", "remove", "--force", "C:/tmp/codex-task14"] in calls


def test_safe_remove_worktree_refuses_locked_worktree_even_when_confirmed_merged(monkeypatch):
    commands = []
    monkeypatch.setattr(git_ops, "run", lambda cmd, check=False, cwd=None: commands.append(cmd) or _cp(cmd))

    removed = git_ops._safe_remove_worktree(
        "C:/tmp/codex-task14",
        "C:/repo",
        confirmed_merged=True,
        locked=True,
    )

    assert removed is False
    assert commands == []


def test_safe_delete_local_branch_refuses_in_use_branch_even_when_confirmed_merged(monkeypatch):
    commands = []
    monkeypatch.setattr(git_ops, "_is_branch_merged_into", lambda branch, base: False)
    monkeypatch.setattr(git_ops, "run", lambda cmd, check=False, cwd=None: commands.append(cmd) or _cp(cmd))

    deleted = git_ops._safe_delete_local_branch(
        "feat/task_13",
        current_branch="dev",
        branch_in_worktrees=True,
        base_branch="dev",
        confirmed_merged=True,
    )

    assert deleted is False
    assert commands == []


def test_git_merge_runs_repo_scoped_from_neutral_directory(monkeypatch):
    merge_calls = []
    cleanup_calls = []

    class _FakeTempDir:
        def __enter__(self):
            return "C:/neutral"

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_view(pr_ref, field, repo=None):
        fields = {
            "headRefName": "feat/task_10",
            "baseRefName": "dev",
            "mergeStateStatus": "CLEAN",
        }
        return fields[field]

    def fake_gh_run(args, repo=None, cwd=None, check=False):
        if args[:2] == ["pr", "merge"]:
            merge_calls.append((args, repo, cwd))
        return _cp(args)

    monkeypatch.setattr(git_ops, "_gh_available", lambda: True)
    monkeypatch.setattr(git_ops, "_origin_repo_slug", lambda: "octo/lab")
    monkeypatch.setattr(git_ops, "_current_branch", lambda: "feat/task_10")
    monkeypatch.setattr(git_ops, "_gh_pr_view_field", fake_view)
    monkeypatch.setattr(git_ops, "monitor_ci", lambda *args, **kwargs: True)
    monkeypatch.setattr(git_ops.tempfile, "TemporaryDirectory", lambda: _FakeTempDir())
    monkeypatch.setattr(git_ops, "_gh_run", fake_gh_run)
    monkeypatch.setattr(
        git_ops,
        "_cleanup_merged_branch_artifacts",
        lambda merged_branch, base_branch, confirmed_merged=False: cleanup_calls.append(
            (merged_branch, base_branch, confirmed_merged)
        ),
    )

    ok = git_ops.git_merge("TASK_10", pr_ref="123")

    assert ok is True
    assert len(merge_calls) == 1
    assert merge_calls[0][0][:3] == ["pr", "merge", "123"]
    assert "--delete-branch" in merge_calls[0][0]
    assert merge_calls[0][1] == "octo/lab"
    assert merge_calls[0][2] == "C:/neutral"
    assert cleanup_calls == [("feat/task_10", "dev", True)]


def test_git_merge_recovers_from_worktree_conflict_without_manual_steps(monkeypatch):
    merge_calls = []
    cleanup_calls = []

    class _FakeTempDir:
        def __enter__(self):
            return "C:/neutral"

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_view(pr_ref, field, repo=None):
        fields = {
            "headRefName": "feat/task_10",
            "baseRefName": "dev",
            "mergeStateStatus": "CLEAN",
        }
        return fields[field]

    def fake_gh_run(args, repo=None, cwd=None, check=False):
        if args[:2] == ["pr", "merge"]:
            merge_calls.append(list(args))
            if "--delete-branch" in args:
                return _cp(args, rc=1, err="fatal: branch is already checked out at another worktree")
            return _cp(args, rc=0)
        return _cp(args)

    monkeypatch.setattr(git_ops, "_gh_available", lambda: True)
    monkeypatch.setattr(git_ops, "_origin_repo_slug", lambda: "octo/lab")
    monkeypatch.setattr(git_ops, "_current_branch", lambda: "feat/task_10")
    monkeypatch.setattr(git_ops, "_gh_pr_view_field", fake_view)
    monkeypatch.setattr(git_ops, "monitor_ci", lambda *args, **kwargs: True)
    monkeypatch.setattr(git_ops.tempfile, "TemporaryDirectory", lambda: _FakeTempDir())
    monkeypatch.setattr(git_ops, "_gh_run", fake_gh_run)
    monkeypatch.setattr(
        git_ops,
        "_cleanup_merged_branch_artifacts",
        lambda merged_branch, base_branch, confirmed_merged=False: cleanup_calls.append(
            (merged_branch, base_branch, confirmed_merged)
        ),
    )

    ok = git_ops.git_merge("TASK_10", pr_ref="123")

    assert ok is True
    assert len(merge_calls) == 2
    assert merge_calls[0] == ["pr", "merge", "123", "--squash", "--delete-branch"]
    assert merge_calls[1] == ["pr", "merge", "123", "--squash"]
    assert cleanup_calls == [("feat/task_10", "dev", True)]


def test_monitor_ci_treats_no_reported_checks_as_success(monkeypatch):
    monkeypatch.setattr(
        git_ops,
        "_gh_run",
        lambda args, repo=None, cwd=None, check=False: _cp(
            args,
            rc=1,
            err="no checks reported on the 'feat/task_11' branch",
        ),
    )

    assert git_ops.monitor_ci("123", poll_seconds=0, max_polls=1, repo="octo/lab") is True


def test_git_merge_allows_merge_when_no_checks_are_reported(monkeypatch):
    merge_calls = []
    cleanup_calls = []

    class _FakeTempDir:
        def __enter__(self):
            return "C:/neutral"

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_view(pr_ref, field, repo=None):
        fields = {
            "headRefName": "feat/task_11",
            "baseRefName": "dev",
            "mergeStateStatus": "CLEAN",
        }
        return fields[field]

    def fake_gh_run(args, repo=None, cwd=None, check=False):
        if args[:2] == ["pr", "checks"]:
            return _cp(args, rc=1, err="no checks reported on the 'feat/task_11' branch")
        if args[:2] == ["pr", "merge"]:
            merge_calls.append((list(args), repo, cwd))
            return _cp(args, rc=0)
        return _cp(args, rc=0)

    monkeypatch.setattr(git_ops, "_gh_available", lambda: True)
    monkeypatch.setattr(git_ops, "_origin_repo_slug", lambda: "octo/lab")
    monkeypatch.setattr(git_ops, "_current_branch", lambda: "feat/task_11")
    monkeypatch.setattr(git_ops, "_gh_pr_view_field", fake_view)
    monkeypatch.setattr(git_ops.tempfile, "TemporaryDirectory", lambda: _FakeTempDir())
    monkeypatch.setattr(git_ops, "_gh_run", fake_gh_run)
    monkeypatch.setattr(
        git_ops,
        "_cleanup_merged_branch_artifacts",
        lambda merged_branch, base_branch, confirmed_merged=False: cleanup_calls.append(
            (merged_branch, base_branch, confirmed_merged)
        ),
    )

    ok = git_ops.git_merge("TASK_11", pr_ref="123")

    assert ok is True
    assert merge_calls == [(["pr", "merge", "123", "--squash", "--delete-branch"], "octo/lab", "C:/neutral")]
    assert cleanup_calls == [("feat/task_11", "dev", True)]
