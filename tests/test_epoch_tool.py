"""
tests/test_epoch_tool.py
Unit tests for autodna/tools/epoch.py retry helper.
"""

import subprocess
from unittest.mock import patch

from autodna.tools.epoch import parse_improve_args, run_with_retries


class FakeProcess:
    def __init__(self, *, returncode=0, stdout=b"", stderr=b"", timeout=False):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._timeout = timeout
        self.pid = 123

    def communicate(self, timeout=None):
        if self._timeout:
            raise subprocess.TimeoutExpired("cmd", timeout=timeout)
        return self._stdout, self._stderr

    def wait(self):
        return self.returncode


def test_run_with_retries_succeeds_after_failure():
    processes = [
        FakeProcess(returncode=1, stdout=b"fail"),
        FakeProcess(returncode=0, stdout=b"ok"),
    ]

    with patch("subprocess.Popen", side_effect=processes) as mock_popen:
        ok = run_with_retries(["cmd"], attempts=2, delay_seconds=0, timeout_seconds=1, label="test")
        assert ok is True
        assert mock_popen.call_count == 2


def test_run_with_retries_fails_after_exhaustion():
    processes = [
        FakeProcess(timeout=True),
        FakeProcess(timeout=True),
    ]

    with patch("subprocess.Popen", side_effect=processes) as mock_popen:
        with patch("subprocess.run") as mock_taskkill:
            ok = run_with_retries(["cmd"], attempts=2, delay_seconds=0, timeout_seconds=1, label="test")
            assert ok is False
            assert mock_popen.call_count == 2
            assert mock_taskkill.call_count == 2


def test_run_with_retries_autofix_memory_then_retry():
    processes = [
        FakeProcess(
            returncode=1,
            stdout=b"UnicodeDecodeError: 'utf-8' codec can't decode byte in MEMORY.md",
        ),
        FakeProcess(returncode=0, stdout=b"ok"),
    ]

    with patch("subprocess.Popen", side_effect=processes) as mock_popen:
        with patch("autodna.tools.epoch._normalize_memory_file", return_value=True) as mock_fix:
            ok = run_with_retries(["cmd"], attempts=2, delay_seconds=0, timeout_seconds=1, label="test")
            assert ok is True
            assert mock_popen.call_count == 2
            mock_fix.assert_called_once()


def test_parse_improve_args_uses_env():
    with patch.dict("os.environ", {"AUTODNA_IMPROVE_ARGS": '--apply-cmd "echo hi"'}):
        args = parse_improve_args([])
        assert "--apply-cmd" in args
