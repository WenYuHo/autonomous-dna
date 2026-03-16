"""
autodna/core/cli_driver.py
Abstracts away specific CLI commands (Gemini, Claude, Aider)
allowing the agent runner to be completely agnostic to the underlying LLM platform.
"""

from typing import List
from pathlib import Path
import os
import shlex
import shutil
import sys

class BaseDriver:
    def get_command(self, model: str, mission: str) -> List[str]:
        raise NotImplementedError

    def is_quota_exhausted(self, line: str) -> bool:
        return False

class GeminiDriver(BaseDriver):
    def get_command(self, model: str, mission: str) -> List[str]:
        # Uses the legacy /ralph:loop syntax specific to Gemini CLI
        return [
            "gemini.cmd",
            "--prompt",
            f'/ralph:loop "{mission}"',
            "--yolo",
            "--model",
            model
        ]

    def is_quota_exhausted(self, line: str) -> bool:
        return "exhausted your capacity on this model" in line or "QUOTA_EXHAUSTED" in line

class ClaudeDriver(BaseDriver):
    def get_command(self, model: str, mission: str) -> List[str]:
        # Claude Code prefers generic shell invocation
        return [
            "claude",
            "-p",
            mission
        ]

    def is_quota_exhausted(self, line: str) -> bool:
        # Catch standard Anthropic rate limits
        return "429 Too Many Requests" in line or "rate limit exceeded" in line.lower()

class AiderDriver(BaseDriver):
    def get_command(self, model: str, mission: str) -> List[str]:
        return [
            "aider",
            "--message",
            mission,
            "--yes",
            "--model",
            model
        ]

    def is_quota_exhausted(self, line: str) -> bool:
        return "429" in line and "rate limit" in line.lower()

class CodexDriver(BaseDriver):
    def get_command(self, model: str, mission: str) -> List[str]:
        cmd = os.environ.get("AUTODNA_CODEX_CMD", "codex")
        if os.name == "nt" and cmd.lower() == "codex":
            for candidate in ("codex.cmd", "codex.exe", "codex"):
                resolved = shutil.which(candidate)
                if resolved:
                    cmd = resolved
                    break
        prompt_flag = os.environ.get("AUTODNA_CODEX_PROMPT_FLAG")
        model_flag = os.environ.get("AUTODNA_CODEX_MODEL_FLAG", "--model")
        extra_args = os.environ.get("AUTODNA_CODEX_EXTRA_ARGS", "")
        if not extra_args and not sys.stdin.isatty():
            # Non-interactive sessions need exec mode to avoid TTY errors.
            extra_args = "exec --full-auto"

        if Path(cmd).exists():
            cmd_parts = [cmd]
        else:
            cmd_parts = shlex.split(cmd, posix=(os.name != "nt"))
        extra_parts = shlex.split(extra_args, posix=(os.name != "nt")) if extra_args else []
        command = cmd_parts + extra_parts
        if model:
            command += [model_flag, model]
        if prompt_flag:
            command += [prompt_flag, mission]
        else:
            command += [mission]
        return command

    def is_quota_exhausted(self, line: str) -> bool:
        return "rate limit" in line.lower() or "quota" in line.lower()

def get_driver(platform_name: str) -> BaseDriver:
    plat = platform_name.strip().upper()
    if plat in {"CLAUDE_CODE", "CLAUDE-CODE", "CLAUDE"}:
        return ClaudeDriver()
    elif plat == "AIDER":
        return AiderDriver()
    elif plat in {"CODEX", "CODEX_APP", "CODEX_DESKTOP", "CODEX_CLI", "OPENAI"}:
        return CodexDriver()
    elif plat in {"GEMINI", "GEMINI_CLI", "GEMINI-CLI", "ANTIGRAVITY"}:
        return GeminiDriver()
    # Default to Gemini if unknown or specifically requested
    return GeminiDriver()
