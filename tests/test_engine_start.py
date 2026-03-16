from pathlib import Path
from tempfile import TemporaryDirectory

from autodna.core import engine_start


def test_is_worktree_dir_false_when_missing():
    with TemporaryDirectory() as tmp:
        assert not engine_start._is_worktree_dir(Path(tmp))


def test_is_worktree_dir_true_for_git_dir():
    with TemporaryDirectory() as tmp:
        path = Path(tmp)
        (path / ".git").mkdir()
        assert engine_start._is_worktree_dir(path)


def test_is_worktree_dir_true_for_git_file():
    with TemporaryDirectory() as tmp:
        path = Path(tmp)
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
