"""
tests/test_epoch_tool.py
Unit tests for autodna/tools/epoch.py retry helper.
"""

from unittest.mock import patch
import subprocess

from autodna.tools.epoch import run_with_retries, parse_improve_args


def test_run_with_retries_succeeds_after_failure():
    calls = {"count": 0}

    def fake_run(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] < 2:
            raise subprocess.CalledProcessError(1, "cmd")
        return 0

    with patch("subprocess.run", side_effect=fake_run):
        ok = run_with_retries(["cmd"], attempts=2, delay_seconds=0, timeout_seconds=1, label="test")
        assert ok is True
        assert calls["count"] == 2


def test_run_with_retries_fails_after_exhaustion():
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired("cmd", timeout=1)

    with patch("subprocess.run", side_effect=fake_run):
        ok = run_with_retries(["cmd"], attempts=2, delay_seconds=0, timeout_seconds=1, label="test")
        assert ok is False


def test_parse_improve_args_uses_env():
    with patch.dict("os.environ", {"AUTODNA_IMPROVE_ARGS": "--apply-cmd \"echo hi\""}):
        args = parse_improve_args([])
        assert "--apply-cmd" in args
