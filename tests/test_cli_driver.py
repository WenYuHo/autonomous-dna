"""
tests/test_cli_driver.py
Unit tests for autodna/core/cli_driver.py — multi-platform CLI driver abstraction.
"""

import os
import unittest
from autodna.core.cli_driver import (
    get_driver,
    GeminiDriver,
    ClaudeDriver,
    AiderDriver,
    CodexDriver,
    BaseDriver,
)


class TestGetDriver(unittest.TestCase):
    """Tests for the get_driver() factory function."""

    def test_gemini_platform(self):
        driver = get_driver("GEMINI_CLI")
        self.assertIsInstance(driver, GeminiDriver)

    def test_gemini_is_default(self):
        driver = get_driver("UNKNOWN_PLATFORM")
        self.assertIsInstance(driver, GeminiDriver)

    def test_claude_platform(self):
        driver = get_driver("CLAUDE_CODE")
        self.assertIsInstance(driver, ClaudeDriver)

    def test_aider_platform(self):
        driver = get_driver("AIDER")
        self.assertIsInstance(driver, AiderDriver)

    def test_codex_platform(self):
        driver = get_driver("CODEX")
        self.assertIsInstance(driver, CodexDriver)

    def test_case_insensitive(self):
        driver = get_driver("claude_code")
        self.assertIsInstance(driver, ClaudeDriver)

    def test_whitespace_stripped(self):
        driver = get_driver("  AIDER  ")
        self.assertIsInstance(driver, AiderDriver)

    def test_empty_string_defaults_gemini(self):
        driver = get_driver("")
        self.assertIsInstance(driver, GeminiDriver)


class TestGeminiDriver(unittest.TestCase):
    """Tests for GeminiDriver."""

    def setUp(self):
        self.driver = GeminiDriver()

    def test_get_command_structure(self):
        cmd = self.driver.get_command("gemini-2.5-pro", "Do the thing")
        self.assertEqual(cmd[0], "gemini.cmd")
        self.assertIn("--model", cmd)
        self.assertIn("gemini-2.5-pro", cmd)
        self.assertIn("--yolo", cmd)

    def test_get_command_includes_mission(self):
        cmd = self.driver.get_command("model-x", "Test mission")
        prompt_arg = cmd[cmd.index("--prompt") + 1]
        self.assertIn("Test mission", prompt_arg)

    def test_quota_exhausted_positive(self):
        self.assertTrue(self.driver.is_quota_exhausted(
            "Error: exhausted your capacity on this model"
        ))
        self.assertTrue(self.driver.is_quota_exhausted(
            "QUOTA_EXHAUSTED for gemini-2.5-pro"
        ))

    def test_quota_exhausted_negative(self):
        self.assertFalse(self.driver.is_quota_exhausted("Everything is fine"))
        self.assertFalse(self.driver.is_quota_exhausted(""))


class TestClaudeDriver(unittest.TestCase):
    """Tests for ClaudeDriver."""

    def setUp(self):
        self.driver = ClaudeDriver()

    def test_get_command_structure(self):
        cmd = self.driver.get_command("claude-3", "Build feature")
        self.assertEqual(cmd[0], "claude")
        self.assertIn("-p", cmd)
        self.assertIn("Build feature", cmd)

    def test_quota_exhausted_positive(self):
        self.assertTrue(self.driver.is_quota_exhausted("429 Too Many Requests"))
        self.assertTrue(self.driver.is_quota_exhausted("Rate Limit Exceeded"))

    def test_quota_exhausted_negative(self):
        self.assertFalse(self.driver.is_quota_exhausted("200 OK"))


class TestAiderDriver(unittest.TestCase):
    """Tests for AiderDriver."""

    def setUp(self):
        self.driver = AiderDriver()

    def test_get_command_structure(self):
        cmd = self.driver.get_command("gpt-4", "Fix bug")
        self.assertEqual(cmd[0], "aider")
        self.assertIn("--message", cmd)
        self.assertIn("Fix bug", cmd)
        self.assertIn("--yes", cmd)
        self.assertIn("--model", cmd)
        self.assertIn("gpt-4", cmd)

    def test_quota_exhausted_positive(self):
        self.assertTrue(self.driver.is_quota_exhausted("429 rate limit hit"))

    def test_quota_exhausted_negative(self):
        # Must have BOTH "429" and "rate limit" to trigger
        self.assertFalse(self.driver.is_quota_exhausted("429 server error"))
        self.assertFalse(self.driver.is_quota_exhausted("rate limit warning"))


class TestCodexDriver(unittest.TestCase):
    """Tests for CodexDriver."""

    def setUp(self):
        self.driver = CodexDriver()

    def test_get_command_structure(self):
        cmd = self.driver.get_command("gpt-5", "Do the thing")
        cmd_name = os.path.basename(cmd[0]).lower()
        self.assertIn(cmd_name, {"codex", "codex.cmd", "codex.exe"})
        self.assertIn("Do the thing", cmd)
        self.assertIn("--model", cmd)
        self.assertIn("gpt-5", cmd)

    def test_quota_exhausted_positive(self):
        self.assertTrue(self.driver.is_quota_exhausted("rate limit exceeded"))
        self.assertTrue(self.driver.is_quota_exhausted("quota exceeded"))

    def test_quota_exhausted_negative(self):
        self.assertFalse(self.driver.is_quota_exhausted("everything is fine"))


class TestBaseDriver(unittest.TestCase):
    """Tests for BaseDriver (abstract base)."""

    def test_get_command_raises(self):
        driver = BaseDriver()
        with self.assertRaises(NotImplementedError):
            driver.get_command("model", "mission")

    def test_is_quota_exhausted_default_false(self):
        driver = BaseDriver()
        self.assertFalse(driver.is_quota_exhausted("anything"))


if __name__ == "__main__":
    unittest.main()
