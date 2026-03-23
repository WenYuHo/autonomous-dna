import sys
from datetime import datetime, timezone
from pathlib import Path

from autodna.tools import research


def test_build_artifact_path_timestamped():
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    path = research.build_artifact_path(
        "Hello world!",
        Path("out"),
        timestamped=True,
        now=now,
    )

    assert path.name == "hello_world_20260102T030405000Z.md"


def test_build_artifact_path_plain():
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    path = research.build_artifact_path(
        "Hello world!",
        Path("out"),
        timestamped=False,
        now=now,
    )

    assert path.name == "hello_world.md"


def test_build_fallback_report_contains_status_and_reason():
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    report = research.build_fallback_report(
        "research timeout fallback",
        "agent-browser timed out",
        now=now,
    )

    assert "# Research Report: research timeout fallback" in report
    assert "- Mode: offline fallback" in report
    assert "- Generated: 2026-01-02T03:04:05Z" in report
    assert "- Reason: agent-browser timed out" in report
    assert "Proceed with task generation using this artifact" in report


def test_main_writes_fallback_artifact(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(research, "run_research", lambda *args, **kwargs: "FALLBACK_REQUIRED")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "research.py",
            "timeout",
            "fallback",
            "--out-dir",
            str(tmp_path),
        ],
    )

    research.main()

    artifact_path = tmp_path / "timeout_fallback.md"
    assert artifact_path.exists()
    content = artifact_path.read_text(encoding="utf-8")
    assert "- Mode: offline fallback" in content
    assert "agent-browser search failed or timed out" in content

    captured = capsys.readouterr()
    assert "SIGNAL: FALLBACK_REQUIRED" in captured.out
    assert "[fallback] Saved offline research artifact to:" in captured.out
