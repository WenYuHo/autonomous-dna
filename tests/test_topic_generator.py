from datetime import datetime
from pathlib import Path

import autodna.tools.topic_generator as topic_generator


def test_identify_next_topic_uses_streamlined_frontier_query(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "conductor").mkdir(parents=True, exist_ok=True)
    (tmp_path / "conductor" / "CURRENT_PRACTICE.md").write_text(
        "## 3. RESEARCH FRONTIER\n- **Context Compression**\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(topic_generator.tasks, "load_db", lambda: {"tasks": []})

    selected, reason = topic_generator.identify_next_topic()

    year = datetime.now().year
    assert selected == f"context compression python agents {year} github"
    assert reason == "Strategic Frontier Goal (Streamlined)"


def test_identify_next_topic_uses_year_aware_error_query(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        topic_generator.tasks,
        "load_db",
        lambda: {
            "tasks": [
                {"status": "error", "title": "Subprocess crash", "description": "Subprocess timeout"}
            ]
        },
    )

    selected, reason = topic_generator.identify_next_topic()

    year = datetime.now().year
    assert selected == f"fix subprocess error python {year} best practices"
    assert reason.startswith("Urgent Error Fix:")


def test_identify_next_topic_fallback_persona_is_year_aware(monkeypatch, tmp_path):
    import random

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(topic_generator.tasks, "load_db", lambda: {"tasks": []})
    monkeypatch.setattr(random, "choice", lambda seq: seq[2])

    selected, reason = topic_generator.identify_next_topic()

    year = datetime.now().year
    assert selected == f"agentic workflow patterns comparison {year} blog"
    assert reason == "Exploratory Discovery (Modern Persona)"
