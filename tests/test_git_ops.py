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
