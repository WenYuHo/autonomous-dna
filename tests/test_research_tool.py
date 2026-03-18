from datetime import datetime, timezone
from pathlib import Path

from autodna.tools.research import build_artifact_path


def test_build_artifact_path_timestamped():
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    path = build_artifact_path("Hello world!", Path("out"), timestamped=True, now=now)

    assert path.name == "hello_world_20260102T030405000Z.md"


def test_build_artifact_path_plain():
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    path = build_artifact_path("Hello world!", Path("out"), timestamped=False, now=now)

    assert path.name == "hello_world.md"
