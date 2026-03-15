"""
tests/test_eval_tool.py
Unit tests for autodna/tools/eval.py
"""

import datetime
from unittest.mock import patch
import pytest

from autodna.tools.eval import defragment_tasks, consolidate_memory

@pytest.fixture
def mock_task_queue(tmp_path):
    queue_file = tmp_path / "TASK_QUEUE.md"
    content = """# TASK QUEUE
# LAST_SYNC: 2026-03-10T00:00:00Z

## IN PROGRESS
- [ ] IN_PROGRESS_TASK: Do something

## BACKLOG
- [ ] BACKLOG_TASK: Do something later

## DONE
- [x] OLD_TASK_1: Done thing 1 (Done: 2026-03-01T00:00:00Z)
- [x] OLD_TASK_2: Done thing 2 (Done: 2026-03-01T00:00:00Z)
"""
    queue_file.write_text(content, encoding="utf-8")
    return queue_file

@pytest.fixture
def mock_memory(tmp_path):
    mem_file = tmp_path / "MEMORY.md"
    content = """# MEMORY
- Fact 1
- Fact 2
- Fact 3
"""
    mem_file.write_text(content, encoding="utf-8")
    return mem_file

def test_defragment_tasks_removes_done_items(mock_task_queue):
    with patch("autodna.tools.eval.Path") as mock_path:
        mock_path.return_value = mock_task_queue

        # Run defrag
        now = datetime.datetime(2026, 3, 10, tzinfo=datetime.UTC)
        removed = defragment_tasks(dry_run=False, older_than_days=7, now=now)

        assert removed == 2

        # Verify file contents
        new_content = mock_task_queue.read_text(encoding="utf-8")
        assert "OLD_TASK_1" not in new_content
        assert "OLD_TASK_2" not in new_content
        assert "IN_PROGRESS_TASK" in new_content
        assert "BACKLOG_TASK" in new_content
        assert "## DONE" in new_content

def test_defragment_tasks_dry_run(mock_task_queue):
    with patch("autodna.tools.eval.Path") as mock_path:
        mock_path.return_value = mock_task_queue

        # Run defrag in dry run
        now = datetime.datetime(2026, 3, 10, tzinfo=datetime.UTC)
        removed = defragment_tasks(dry_run=True, older_than_days=7, now=now)

        assert removed == 2

        # Verify file contents were NOT changed
        new_content = mock_task_queue.read_text(encoding="utf-8")
        assert "OLD_TASK_1" in new_content
        assert "OLD_TASK_2" in new_content

def test_defragment_tasks_no_file():
    with patch("autodna.tools.eval.Path") as mock_path:
        mock_path.return_value.exists.return_value = False

        removed = defragment_tasks()
        assert removed == 0

def test_consolidate_memory_counts_facts(mock_memory, capsys):
    with patch("autodna.tools.eval.Path") as mock_path:
        mock_path.return_value = mock_memory

        consolidate_memory()

        captured = capsys.readouterr()
        assert "3 facts tracked" in captured.out

def test_consolidate_memory_warns_over_100(tmp_path, capsys):
    mem_file = tmp_path / "MEMORY.md"
    content = "# MEMORY\n" + "\n".join([f"- Fact {i}" for i in range(105)])
    mem_file.write_text(content, encoding="utf-8")

    with patch("autodna.tools.eval.Path") as mock_path:
        mock_path.return_value = mem_file

        consolidate_memory(dry_run=False)

        captured = capsys.readouterr()
        assert "105 facts tracked" in captured.out
        assert "Warning: MEMORY.md is exceeding max facts" in captured.out


def test_consolidate_memory_prunes_and_archives(tmp_path):
    mem_file = tmp_path / "MEMORY.md"
    content = "# MEMORY\n" + "\n".join([f"- Fact {i}" for i in range(5)])
    mem_file.write_text(content, encoding="utf-8")
    archive_file = tmp_path / "MEMORY_ARCHIVE.md"

    with patch("autodna.tools.eval.Path") as mock_path:
        mock_path.return_value = mem_file
        consolidate_memory(dry_run=False, max_facts=3, prune=True, archive_path=archive_file)

    updated = mem_file.read_text(encoding="utf-8")
    assert "- Fact 0" not in updated
    assert "- Fact 4" in updated
    assert archive_file.exists()
