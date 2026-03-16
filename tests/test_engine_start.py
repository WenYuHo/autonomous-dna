"""
tests/test_engine_start.py
Unit tests for autodna/core/engine_start.py — orchestrator script for swarm launch.
"""

import os
import sys
import unittest
from unittest.mock import patch, mock_open
import pathlib
from tempfile import TemporaryDirectory

from autodna.core import engine_start


class TestEngineStart(unittest.TestCase):

    @patch("subprocess.run")
    @patch("os.path.exists")
    def test_setup_junction_creates_link(self, mock_exists, mock_run):
        # root folder exists, target doesn't -> should create junction
        def mock_exists_logic(path):
            if "target" in str(path):
                return False
            return True
        mock_exists.side_effect = mock_exists_logic

        with patch("os.getcwd", return_value="mock_root"):
            engine_start.setup_junction("mock_target", "folder")

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertIn("mklink /J", cmd)
        self.assertIn("folder", cmd)

    @patch("subprocess.run")
    @patch("os.path.exists")
    def test_setup_junction_skips_if_exists(self, mock_exists, mock_run):
        # target already exists -> no op
        mock_exists.return_value = True

        engine_start.setup_junction("target", "folder")
        mock_run.assert_not_called()

    @patch("subprocess.run")
    @patch("pathlib.Path.exists")
    def test_setup_worktree_runs_git(self, mock_exists, mock_run):
        # name dir doesn't exist
        mock_exists.return_value = False
        mock_run.return_value.returncode = 0

        with patch("autodna.core.engine_start.setup_junction") as mock_junction:
            with patch("autodna.core.engine_start._branch_exists", return_value=False):
                engine_start.setup_worktree("worker-3")

            mock_run.assert_called_once_with(
                ["git", "worktree", "add", "worker-3", "-b", "autodna-worker-3"],
                shell=False,
            )

            # Should setup 4 junctions
            self.assertEqual(mock_junction.call_count, 4)
            calls = mock_junction.call_args_list
            self.assertEqual(calls[0][0], ("worker-3", ".venv"))
            self.assertEqual(calls[1][0], ("worker-3", "node_modules"))
            self.assertEqual(calls[2][0], ("worker-3", "models"))
            self.assertEqual(calls[3][0], ("worker-3", "agent"))

    @patch("subprocess.run")
    @patch("pathlib.Path.exists")
    def test_setup_worktree_fails(self, mock_exists, mock_run):
        mock_exists.return_value = False
        mock_run.return_value.returncode = 128

        with patch("autodna.core.engine_start._branch_exists", return_value=False):
            with self.assertRaises(SystemExit):
                engine_start.setup_worktree("worker-3")

    @patch("subprocess.run")
    def test_launch_agent_interactive(self, mock_run):
        result = engine_start.launch_agent("test-agent", "Do stuff", color="0C", headless=False)
        self.assertIsNone(result)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertIn("start \"AUTODNA-test-agent\" cmd /k", cmd)
        self.assertIn("color 0C", cmd)
        self.assertIn("cd test-agent", cmd)
        self.assertIn("Do stuff", cmd)
        self.assertIn("GPU SAFETY", cmd)

    @patch("subprocess.Popen")
    def test_launch_agent_headless(self, mock_popen):
        m = mock_open()
        with patch("builtins.open", m):
            with patch.object(pathlib.Path, "cwd", return_value=pathlib.Path("/tmp")):
                result = engine_start.launch_agent("worker-1", "Headless mission", headless=True)

                # Should return path to log file
                self.assertEqual(str(result), os.path.normpath("/tmp/agent/worker-1.log"))

                # Should have opened log file for writing
                m.assert_called_once_with(os.path.normpath("/tmp/agent/worker-1.log"), "w", encoding="utf-8")

                # Should have used Popen
                mock_popen.assert_called_once()
                cmd_list = mock_popen.call_args[0][0]
                self.assertEqual(cmd_list[0], "python")
                self.assertEqual(cmd_list[2], "autodna.core.agent_runner")
                self.assertEqual(cmd_list[3], "worker-1")
                self.assertIn("Headless mission", cmd_list[4])

    @patch("autodna.core.engine_start.launch_agent")
    @patch("autodna.core.engine_start.setup_worktree")
    @patch("os.path.exists")
    @patch("os.remove")
    @patch("time.sleep")
    def test_main_interactiveflow(self, mock_sleep, mock_remove, mock_exists, mock_setup, mock_launch):
        # Simulate lock file existing
        mock_exists.return_value = True

        with patch.object(sys, "argv", ["engine_start.py"]):
            engine_start.main()

            # Removed lock
            mock_remove.assert_called_once()

            # Sub-agents set up
            self.assertEqual(mock_setup.call_count, 2)
            mock_setup.assert_any_call("worker-1")
            mock_setup.assert_any_call("worker-2")

            # 3 agents launched
            self.assertEqual(mock_launch.call_count, 3)
            calls = mock_launch.call_args_list

            # First is manager (.)
            self.assertEqual(calls[0][0][0], ".")
            self.assertFalse(calls[0][1].get("headless", True))

            # Then workers
            self.assertEqual(calls[1][0][0], "worker-1")
            self.assertEqual(calls[2][0][0], "worker-2")


def test_is_worktree_dir_false_when_missing():
    with TemporaryDirectory() as tmp:
        assert not engine_start._is_worktree_dir(pathlib.Path(tmp))


def test_is_worktree_dir_true_for_git_dir():
    with TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp)
        (path / ".git").mkdir()
        assert engine_start._is_worktree_dir(path)


def test_is_worktree_dir_true_for_git_file():
    with TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp)
        (path / ".git").write_text("gitdir: /fake/path")
        assert engine_start._is_worktree_dir(path)


def test_manager_mission_uses_python_cli():
    mission = engine_start.build_manager_mission()
    assert "python -m autodna.cli" in mission
    assert "autodna tasks list" in mission


def test_worker_mission_uses_python_cli_and_folder():
    mission = engine_start.build_worker_mission("Worker-1", "worker-1")
    assert "python -m autodna.cli" in mission
    assert "tasks claim <id> worker-1" in mission
    assert "Stay in worker-1 folder" in mission


if __name__ == "__main__":
    unittest.main()
