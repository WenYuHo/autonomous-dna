"""
tests/test_improve_tool.py
Unit tests for autodna/tools/improve.py helpers.
"""

from unittest.mock import patch

import pytest

from autodna.tools.improve import ensure_clean_working_tree, run_command, compare_and_gate


def test_ensure_clean_working_tree_raises_on_dirty():
    class Result:
        stdout = " M dirty.txt\n"

    with patch("subprocess.run", return_value=Result()):
        with pytest.raises(SystemExit):
            ensure_clean_working_tree()


def test_run_command_success():
    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    with patch("subprocess.run", return_value=Result()):
        ok, out, err = run_command(["echo", "ok"], timeout=1, shell=False)
        assert ok is True
        assert out == "ok"
        assert err == ""


def test_compare_and_gate_detects_failure(tmp_path):
    baseline = tmp_path / "baseline.md"
    after = tmp_path / "after.md"

    baseline.write_text(
        "# Dogfood Report\n"
        "- Memory facts: 10\n"
        "- Task counts: in_progress=1, backlog=1, done=1\n",
        encoding="utf-8",
    )
    after.write_text(
        "# Dogfood Report\n"
        "- Memory facts: 12\n"
        "- Task counts: in_progress=2, backlog=3, done=2\n",
        encoding="utf-8",
    )

    failures, _summary = compare_and_gate(
        baseline_path=baseline,
        after_path=after,
        gates=["backlog_delta<=0"],
        use_default_gates=False,
    )
    assert any("backlog_delta<=0" in failure for failure in failures)
