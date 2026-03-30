import os
import pathlib
import subprocess
import sys
from unittest.mock import mock_open, patch

from autodna.core import engine_start


def test_resolve_platform_prefers_env(monkeypatch):
    monkeypatch.setenv("AUTODNA_PLATFORM", "CODEX")
    assert engine_start.resolve_platform() == "CODEX"


def test_resolve_platform_uses_active_file(monkeypatch, tmp_path):
    monkeypatch.delenv("AUTODNA_PLATFORM", raising=False)
    active = tmp_path / "platform" / "ACTIVE"
    active.parent.mkdir(parents=True)
    active.write_text("ANTIGRAVITY\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert engine_start.resolve_platform() == "ANTIGRAVITY"


def test_build_agent_mission_for_specific_task():
    mission = engine_start.build_agent_mission("autodna", 12)
    assert "Single-Agent Mode" in mission
    assert "task 12" in mission
    assert "tasks claim 12 autodna" in mission
    assert "tasks complete 12" in mission
    assert "controller will rerun the required tests and dogfood evaluation" in mission
    assert "inspect leftover modified/untracked files" in mission
    assert "brainstorm one small adjacent improvement" in mission


def test_build_agent_mission_without_task():
    mission = engine_start.build_agent_mission("autodna")
    assert "Resume any task already assigned to you" in mission
    assert "tasks claim <id> autodna" in mission
    assert "controller will rerun the required tests and dogfood evaluation" in mission
    assert "Stay in the main workspace" in mission
    assert "tasks add" in mission


def test_build_agent_mission_includes_worktree_summary_when_available():
    with patch.object(engine_start, "_worktree_summary_for_mission", return_value="Current worktree summary: clean."):
        mission = engine_start.build_agent_mission("autodna", 7)
    assert "Current worktree summary: clean." in mission


def test_worktree_summary_parses_porcelain_output():
    status = subprocess.CompletedProcess(
        ["git", "status", "--porcelain"],
        0,
        " M tools/self_improve.py\n?? agent/run_outcomes/\nR  old.py -> new.py\n",
        "",
    )
    with patch("subprocess.run", return_value=status):
        summary = engine_start._worktree_summary_for_mission(max_items=2)
    assert "3 file(s)" in summary
    assert "agent/run_outcomes/" in summary or "tools/self_improve.py" in summary or "new.py" in summary
    assert "+1 more" in summary


@patch("subprocess.run")
def test_launch_agent_interactive(mock_run):
    result = engine_start.launch_agent("test-agent", "Do stuff", color="0C", headless=False)
    assert result is None

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert 'start "AUTODNA-test-agent" cmd /k' in cmd
    assert "color 0C" in cmd
    assert "python -m autodna.core.agent_runner test-agent" in cmd
    assert "Do stuff" in cmd
    assert "GPU SAFETY" in cmd


@patch("subprocess.Popen")
def test_launch_agent_headless(mock_popen):
    m = mock_open()
    with patch("builtins.open", m):
        with patch.object(pathlib.Path, "cwd", return_value=pathlib.Path("/tmp")):
            result = engine_start.launch_agent("agent one", "Headless mission", headless=True)

    assert str(result) == os.path.normpath("/tmp/agent/agent-one.log")
    m.assert_called_once_with(os.path.normpath("/tmp/agent/agent-one.log"), "w", encoding="utf-8")

    mock_popen.assert_called_once()
    cmd_list = mock_popen.call_args[1]["args"] if "args" in mock_popen.call_args[1] else mock_popen.call_args[0][0]
    assert cmd_list[0] == "python"
    assert cmd_list[2] == "autodna.core.agent_runner"
    assert cmd_list[3] == "agent-one"
    assert "Headless mission" in cmd_list[4]


@patch("autodna.core.engine_start.launch_agent")
@patch("os.path.exists")
@patch("pathlib.Path.exists")
@patch("pathlib.Path.unlink")
def test_main_interactive_flow(mock_unlink, mock_gpu_exists, mock_git_exists, mock_launch):
    mock_git_exists.return_value = True
    mock_gpu_exists.return_value = True

    with patch.object(sys, "argv", ["engine_start.py"]):
        engine_start.main()

    mock_unlink.assert_called_once()
    mock_launch.assert_called_once()
    assert mock_launch.call_args[0][0] == "autodna"
    assert mock_launch.call_args[1]["headless"] is False


@patch("autodna.core.engine_start.launch_agent")
@patch("os.path.exists")
@patch("pathlib.Path.exists")
def test_main_headless_flow(mock_gpu_exists, mock_git_exists, mock_launch):
    mock_git_exists.return_value = True
    mock_gpu_exists.return_value = False
    mock_launch.return_value = pathlib.Path("/tmp/agent/autodna.log")

    with patch.object(sys, "argv", ["engine_start.py", "--headless", "--agent-name", "codex", "--task-id", "17"]):
        engine_start.main()

    assert mock_launch.call_args[0][0] == "codex"
    assert "task 17" in mock_launch.call_args[0][1]
    assert mock_launch.call_args[1]["headless"] is True
