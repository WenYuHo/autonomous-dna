"""
autodna/core/cli_driver.py
Abstracts away specific CLI commands (Gemini, Claude, Aider)
allowing the agent runner to be completely agnostic to the underlying LLM platform.
"""

from typing import List

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

def get_driver(platform_name: str) -> BaseDriver:
    plat = platform_name.strip().upper()
    if plat == "CLAUDE_CODE":
        return ClaudeDriver()
    elif plat == "AIDER":
        return AiderDriver()
    # Default to Gemini if unknown or specifically requested
    return GeminiDriver()
