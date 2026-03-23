import os
import subprocess

import pytest

from tools import git_ops


def test_resolve_base_branch_prefers_env(monkeypatch):
    monkeypatch.setenv("AUTODNA_GIT_BASE_BRANCH", "dev")
    monkeypatch.setattr(git_ops, "_branch_exists", lambda name: name == "dev")
    assert git_ops.resolve_base_branch() == "dev"


def test_run_tests_skips_when_disabled(monkeypatch):
    monkeypatch.setenv("AUTODNA_GIT_TEST_CMD", "")
    called = {"count": 0}

    def fake_run(cmd, check=False):
        called["count"] += 1
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(git_ops, "run", fake_run)
    git_ops.run_tests()
    assert called["count"] == 0


def test_run_tests_exits_on_failure(monkeypatch):
    monkeypatch.setenv("AUTODNA_GIT_TEST_CMD", "python -m pytest tests/")

    def fake_run(cmd, check=False):
        return subprocess.CompletedProcess(cmd, 1, "fail", "fail")

    monkeypatch.setattr(git_ops, "run", fake_run)
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
            subprocess.CompletedProcess(
                ["git", "status"],
                0,
                "\n".join(
                    [
                        "# branch.oid abcdef",
                        "# branch.head dev",
                        "# branch.upstream origin/dev",
                        "# branch.ab +4 -0",
                        "1 .M N... 100644 100644 100644 file.py file.py",
                    ]
                ),
                "",
            ),
            subprocess.CompletedProcess(
                ["git", "fetch"],
                0,
                "",
                "",
            ),
            subprocess.CompletedProcess(
                ["git", "status"],
                0,
                "\n".join(
                    [
                        "# branch.oid abcdef",
                        "# branch.head dev",
                        "# branch.upstream origin/dev",
                        "# branch.ab +4 -0",
                        "1 .M N... 100644 100644 100644 file.py file.py",
                    ]
                ),
                "",
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
    status = subprocess.CompletedProcess(
        ["git", "status"],
        0,
        "\n".join(
            [
                "# branch.oid abcdef",
                "# branch.head dev",
            ]
        ),
        "",
    )

    monkeypatch.setattr(git_ops.os.path, "exists", lambda path: path == ".git")
    monkeypatch.setattr(git_ops, "run", lambda args, check=False: status)

    state = git_ops.inspect_git_state(fetch=False)

    assert state["ok"] is False
    assert "Current branch has no upstream tracking branch." in state["issues"]
