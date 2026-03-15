"""
tests/test_trace_logger.py
Unit tests for tools/trace_logger.py — Autonomous-DNA observability system.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Add project root to path so we can import trace_logger
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

import trace_logger


class TestTraceLogger(unittest.TestCase):
    """Tests for the trace logging system."""

    def setUp(self):
        """Create a temporary directory to simulate the project root."""
        self.test_dir = tempfile.mkdtemp()
        self.original_traces_dir = trace_logger.TRACES_DIR
        self.original_session_file = trace_logger.CURRENT_SESSION_FILE

        # Redirect trace_logger paths to temp dir
        trace_logger.TRACES_DIR = Path(self.test_dir) / "agent" / "traces"
        trace_logger.CURRENT_SESSION_FILE = trace_logger.TRACES_DIR / ".current_session"

    def tearDown(self):
        """Clean up temp directory and restore original paths."""
        shutil.rmtree(self.test_dir, ignore_errors=True)
        trace_logger.TRACES_DIR = self.original_traces_dir
        trace_logger.CURRENT_SESSION_FILE = self.original_session_file

    def test_log_creates_jsonl_file(self):
        """Test that log_action creates a valid JSONL file."""
        session_id = trace_logger.log_action(
            action="session_start",
            session_id="test123",
            platform="test",
        )

        trace_file = trace_logger.TRACES_DIR / f"{session_id}.jsonl"
        self.assertTrue(trace_file.exists(), "Trace file should be created")

        with open(trace_file, "r") as f:
            line = f.readline().strip()
            entry = json.loads(line)

        self.assertEqual(entry["session_id"], "test123")
        self.assertEqual(entry["action"], "session_start")
        self.assertEqual(entry["platform"], "test")
        self.assertIsNotNone(entry["timestamp"])

    def test_log_appends_multiple_entries(self):
        """Test that multiple log calls append to the same session file."""
        sid = "multi_test"
        trace_logger.log_action(action="reserve", session_id=sid, platform="test", task_id=101)
        trace_logger.log_action(action="plan", session_id=sid, platform="test", task_id=101)
        trace_logger.log_action(action="implement", session_id=sid, platform="test",
                                task_id=101, files_touched=["tools/x.py"])

        trace_file = trace_logger.TRACES_DIR / f"{sid}.jsonl"
        with open(trace_file, "r") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]

        self.assertEqual(len(lines), 3, "Should have 3 trace entries")

        entries = [json.loads(l) for l in lines]
        self.assertEqual(entries[0]["action"], "reserve")
        self.assertEqual(entries[1]["action"], "plan")
        self.assertEqual(entries[2]["action"], "implement")
        self.assertEqual(entries[2]["files_touched"], ["tools/x.py"])

    def test_read_trace(self):
        """Test reading trace entries back from file."""
        sid = "read_test"
        trace_logger.log_action(action="reserve", session_id=sid, platform="test")
        trace_logger.log_action(action="done", session_id=sid, platform="test")

        entries = trace_logger.read_trace(sid)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["action"], "reserve")
        self.assertEqual(entries[1]["action"], "done")

    def test_format_summary(self):
        """Test that summary formatting produces readable output."""
        sid = "summary_test"
        trace_logger.log_action(action="session_start", session_id=sid, platform="antigravity")
        trace_logger.log_action(action="reserve", session_id=sid, platform="antigravity", task_id=101)
        trace_logger.log_action(action="implement", session_id=sid, platform="antigravity",
                                task_id=101, files_touched=["tools/trace_logger.py"])
        trace_logger.log_action(action="verify", session_id=sid, platform="antigravity", task_id=101)
        trace_logger.log_action(action="done", session_id=sid, platform="antigravity", task_id=101)

        entries = trace_logger.read_trace(sid)
        summary = trace_logger.format_summary(entries)

        self.assertIn("summary_test", summary)
        self.assertIn("antigravity", summary)
        self.assertIn("Actions: 5 total", summary)
        self.assertIn("tools/trace_logger.py", summary)

    def test_session_id_persistence(self):
        """Test that session ID is persisted across calls."""
        sid = trace_logger.new_session("test")
        self.assertIsNotNone(sid)

        retrieved = trace_logger.get_current_session()
        self.assertEqual(sid, retrieved)

    def test_new_session_creates_session_start_entry(self):
        """Test that new_session automatically logs a session_start action."""
        sid = trace_logger.new_session("test")
        entries = trace_logger.read_trace(sid)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["action"], "session_start")
        self.assertEqual(entries[0]["platform"], "test")

    def test_invalid_action_rejected(self):
        """Test that invalid actions are rejected."""
        with self.assertRaises(SystemExit):
            trace_logger.log_action(action="invalid_action", session_id="x", platform="test")

    def test_error_field_logged(self):
        """Test that error messages are captured in traces."""
        sid = "error_test"
        trace_logger.log_action(action="error", session_id=sid, platform="test",
                                error="Test failed: assertion error")

        entries = trace_logger.read_trace(sid)
        self.assertEqual(entries[0]["error"], "Test failed: assertion error")

    def test_trace_entry_size(self):
        """Test that individual trace entries are reasonably sized (< 500 bytes)."""
        sid = "size_test"
        trace_logger.log_action(
            action="implement",
            session_id=sid,
            platform="antigravity",
            task_id=102,
            files_touched=["tools/trace_logger.py", "tools/session_start.py"],
        )

        trace_file = trace_logger.TRACES_DIR / f"{sid}.jsonl"
        with open(trace_file, "r") as f:
            line = f.readline()

        self.assertLess(len(line.encode("utf-8")), 500,
                        "Single trace entry should be < 500 bytes")

    def test_empty_trace_summary(self):
        """Test summary handles empty trace gracefully."""
        summary = trace_logger.format_summary([])
        self.assertIn("No trace data", summary)

    def test_latest_trace_file(self):
        """Test that get_latest_trace_file returns most recent file."""
        trace_logger.log_action(action="session_start", session_id="old_session", platform="test")
        import time
        time.sleep(0.1)  # Ensure different mtime
        trace_logger.log_action(action="session_start", session_id="new_session", platform="test")

        latest = trace_logger.get_latest_trace_file()
        self.assertIsNotNone(latest)
        self.assertIn("new_session", latest.name)


if __name__ == "__main__":
    unittest.main()
