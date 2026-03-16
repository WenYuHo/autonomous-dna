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
            return subprocess.CompletedProcess(args, 1, stdout="fail", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

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


def test_run_with_retries_autofix_memory_then_retry():
    calls = {"count": 0}

    def fake_run(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return subprocess.CompletedProcess(
                args,
                1,
                stdout="UnicodeDecodeError: 'utf-8' codec can't decode byte in MEMORY.md",
                stderr="",
            )
        return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

    with patch("subprocess.run", side_effect=fake_run):
        with patch("autodna.tools.epoch._normalize_memory_file", return_value=True) as mock_fix:
            ok = run_with_retries(["cmd"], attempts=2, delay_seconds=0, timeout_seconds=1, label="test")
            assert ok is True
            assert calls["count"] == 2
            mock_fix.assert_called_once()


def test_parse_improve_args_uses_env():
    with patch.dict("os.environ", {"AUTODNA_IMPROVE_ARGS": "--apply-cmd \"echo hi\""}):
        args = parse_improve_args([])
        assert "--apply-cmd" in args
