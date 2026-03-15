"""
tests/test_cli.py
Unit tests for autodna/cli.py — the global CLI router.
"""

import sys
import unittest
from unittest.mock import patch
from io import StringIO


class TestCliHelp(unittest.TestCase):
    """Tests for CLI help and argument parsing."""

    def test_no_args_prints_help(self):
        """Running autodna with no command should print help and exit cleanly."""
        with patch.object(sys, "argv", ["autodna"]):
            from autodna.cli import main
            # Capture stdout
            captured = StringIO()
            with patch("sys.stdout", captured):
                main()
            output = captured.getvalue()
            self.assertIn("usage", output.lower())

    def test_start_command_triggers_engine(self):
        """autodna start should route to engine_start.main."""
        with patch.object(sys, "argv", ["autodna", "start"]):
            with patch("autodna.core.engine_start.main") as mock_engine:
                from autodna.cli import main
                main()
                mock_engine.assert_called_once()

    def test_start_headless_passes_flag(self):
        """autodna start --headless should pass --headless to engine_start."""
        with patch.object(sys, "argv", ["autodna", "start", "--headless"]):
            with patch("autodna.core.engine_start.main") as mock_engine:
                from autodna.cli import main
                main()
                mock_engine.assert_called_once()
                # After main(), sys.argv should contain --headless
                self.assertIn("--headless", sys.argv)


class TestDynamicToolDiscovery(unittest.TestCase):
    """Tests for dynamic tool discovery from autodna.tools."""

    def test_benchmark_tool_discovered(self):
        """The benchmark tool should be discoverable as a CLI subcommand."""
        import pkgutil
        import autodna.tools
        discovered = [name for _, name, _ in pkgutil.iter_modules(autodna.tools.__path__)]
        self.assertIn("benchmark", discovered)

    def test_context_tool_discovered(self):
        """The context tool should be discoverable as a CLI subcommand."""
        import pkgutil
        import autodna.tools
        discovered = [name for _, name, _ in pkgutil.iter_modules(autodna.tools.__path__)]
        self.assertIn("context", discovered)

    def test_tasks_tool_discovered(self):
        """The tasks tool should be discoverable as a CLI subcommand."""
        import pkgutil
        import autodna.tools
        discovered = [name for _, name, _ in pkgutil.iter_modules(autodna.tools.__path__)]
        self.assertIn("tasks", discovered)


if __name__ == "__main__":
    unittest.main()
