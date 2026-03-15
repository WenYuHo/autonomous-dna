"""
tests/test_agent_runner.py
Unit tests for autodna/core/agent_runner.py — the process wrapper that manages LLM model fallbacks.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import subprocess

from autodna.core import agent_runner


class MockProcess:
    def __init__(self, stdout_lines, returncode=0):
        self._stdout_lines = stdout_lines
        self.returncode = returncode
        self._poll_called = 0
        self._terminated = False
        self._killed = False
        self._waited = False

        # Create a mock for stdout
        self.stdout = MagicMock()

        # We need readline to return lines sequentially, then empty strings
        def mock_readline():
            if self._stdout_lines:
                return self._stdout_lines.pop(0)
            return ""

        self.stdout.readline.side_effect = mock_readline

    def poll(self):
        # We simulate the process ending after all stdout lines are consumed
        if not self._stdout_lines:
            return self.returncode
        return None

    def terminate(self):
        self._terminated = True

    def kill(self):
        self._killed = True

    def wait(self, timeout=None):
        self._waited = True
        return self.returncode


class TestAgentRunner(unittest.TestCase):
    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {"AUTODNA_MODELS": "model-1,model-2"})
        self.env_patcher.start()

        self.sleep_patcher = patch("time.sleep")
        self.sleep_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()
        self.sleep_patcher.stop()

    def test_missing_args(self):
        with patch.object(sys, "argv", ["agent_runner.py"]):
            with self.assertRaises(SystemExit):
                agent_runner.main()

    @patch("subprocess.Popen")
    def test_clean_exit_first_model(self, mock_popen):
        # The agent writes some lines and exits cleanly
        mock_process = MockProcess(["Thinking...\n", "Done!\n"], returncode=0)
        mock_popen.return_value = mock_process

        with patch.object(sys, "argv", ["agent_runner.py", "AgentX", "My Mission"]):
            with patch("sys.stdout", new=MagicMock()) as mock_stdout:
                agent_runner.main()

        # Should only call Popen once because it succeeded
        mock_popen.assert_called_once()
        # Ensure it passed the first model
        cmd = mock_popen.call_args[0][0]
        self.assertIn("model-1", cmd)

    @patch("subprocess.Popen")
    @patch("autodna.core.cli_driver.get_driver")
    def test_quota_exhausted_fallback(self, mock_get_driver, mock_popen):
        # Setup the mock driver to flag exhaustion
        mock_driver = MagicMock()
        mock_driver.get_command.side_effect = lambda model, mission: ["cmd", model, mission]
        # It flags quota exhausted if "quota" is in the line
        mock_driver.is_quota_exhausted.side_effect = lambda line: "quota" in line.lower()
        mock_get_driver.return_value = mock_driver

        # First process: fails with quota exhausted immediately
        proc1 = MockProcess(["Starting...\n", "Error: Quota reached!\n"], returncode=1)
        # Second process: completes successfully
        proc2 = MockProcess(["Success with model 2\n"], returncode=0)

        mock_popen.side_effect = [proc1, proc2]

        with patch.object(sys, "argv", ["agent_runner.py", "AgentX", "Mission"]):
            with patch("sys.stdout", new=MagicMock()):
                agent_runner.main()

        # Called twice: once for model-1, once for fallback model-2
        self.assertEqual(mock_popen.call_count, 2)

        cmd1 = mock_popen.call_args_list[0][0][0]
        cmd2 = mock_popen.call_args_list[1][0][0]
        self.assertEqual(cmd1[1], "model-1")
        self.assertEqual(cmd2[1], "model-2")

    @patch("subprocess.Popen")
    def test_crash_retries_same_model(self, mock_popen):
        # Process crashes (non-quota error) with returncode 1
        proc1 = MockProcess(["Crash 1\n"], returncode=1)
        proc2 = MockProcess(["Crash 2\n"], returncode=1)
        proc3 = MockProcess(["Crash 3\n"], returncode=1)
        # After 3 crashes, it should switch to model-2
        proc4 = MockProcess(["Success\n"], returncode=0)

        mock_popen.side_effect = [proc1, proc2, proc3, proc4]

        with patch.object(sys, "argv", ["agent_runner.py", "AgentX", "Mission"]):
            with patch("sys.stdout", new=MagicMock()):
                agent_runner.main()

        # Should have called Popen 4 times (3 retries for model-1, 1 for model-2)
        self.assertEqual(mock_popen.call_count, 4)

        # Verify it used model-1 for the first 3
        for i in range(3):
            cmd = mock_popen.call_args_list[i][0][0]
            self.assertIn("model-1", cmd)

        # Verify it switched to model-2 for the 4th
        cmd = mock_popen.call_args_list[3][0][0]
        self.assertIn("model-2", cmd)

    @patch("subprocess.Popen")
    def test_all_models_exhausted(self, mock_popen):
        # Both models crash 3 times
        proc_crash = lambda: MockProcess(["Crash\n"], returncode=1)
        mock_popen.side_effect = [
            proc_crash(), proc_crash(), proc_crash(), # model-1
            proc_crash(), proc_crash(), proc_crash()  # model-2
        ]

        with patch.object(sys, "argv", ["agent_runner.py", "AgentX", "Mission"]):
            with patch("sys.stdout", new=MagicMock()) as mock_stdout:
                agent_runner.main()

        self.assertEqual(mock_popen.call_count, 6)

    @patch("subprocess.Popen")
    def test_subprocess_timeout_cleanup(self, mock_popen):
        # Test the emergency cleanup block when a process freezes
        proc = MockProcess(["QUOTA EXHAUSTED\n"], returncode=None)
        # Force poll to return None so runner thinks it's still alive
        proc.poll = MagicMock(return_value=None)

        # Simulate a timeout during wait()
        def mock_wait(timeout=None):
            raise subprocess.TimeoutExpired(cmd="cmd", timeout=timeout)
        proc.wait = mock_wait

        mock_popen.return_value = proc

        # Mock cli driver so it triggers quota exhaustion
        with patch("autodna.core.cli_driver.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_driver.is_quota_exhausted.return_value = True
            mock_get_driver.return_value = mock_driver

            with patch.dict(os.environ, {"AUTODNA_MODELS": "model-1"}):
                with patch.object(sys, "argv", ["agent_runner.py", "AgentX", "Mission"]):
                    with patch("sys.stdout", new=MagicMock()):
                        agent_runner.main()

        # Since wait timed out, it should have killed the process
        self.assertTrue(proc._killed)

if __name__ == "__main__":
    unittest.main()
