from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from autodna.tools.research import build_artifact_path, run_research


def test_build_artifact_path_timestamped():
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    path = build_artifact_path("Hello world!", Path("out"), timestamped=True, now=now)

    assert path.name == "hello_world_20260102T030405000Z.md"


def test_build_artifact_path_plain():
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    path = build_artifact_path("Hello world!", Path("out"), timestamped=False, now=now)

    assert path.name == "hello_world.md"


def test_run_research_uses_timeout_ms_for_session():
    captured = {"timeout": None}

    class FakeSession:
        def __init__(self, session_name="autodna-research", timeout=30):
            captured["timeout"] = timeout

        def run(self, command, json_output=True):
            if command[:2] == ["find", "role"]:
                return ["https://example.com/article"]
            if command == ["get", "text"]:
                return "content"
            if command[:1] in (["open"], ["wait"], ["close"], ["snapshot"]):
                return ""
            return ""

    with patch("autodna.tools.research.AgentBrowserSession", FakeSession):
        report = run_research(
            topic="testing timeout behavior",
            max_sources=1,
            allow_domains=[],
            block_domains=[],
            dedupe_host=True,
            dedupe_url=True,
            timeout_ms=120000,
            retries=1,
        )

    assert captured["timeout"] == 120
    assert "## Source: https://example.com/article" in report


def test_run_research_returns_fallback_on_bot_detection():
    class FakeSession:
        def __init__(self, session_name="autodna-research", timeout=30):
            self.timeout = timeout

        def run(self, command, json_output=True):
            if command[:1] in (["open"], ["wait"], ["close"]):
                return ""
            if command == ["snapshot", "-i"]:
                return "captcha verify you are human"
            return ""

    with patch("autodna.tools.research.AgentBrowserSession", FakeSession):
        result = run_research(
            topic="bot detection",
            max_sources=1,
            allow_domains=[],
            block_domains=[],
            dedupe_host=True,
            dedupe_url=True,
            timeout_ms=15000,
            retries=1,
        )

    assert result == "FALLBACK_REQUIRED"
