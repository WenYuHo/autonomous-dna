"""
tests/test_dogfood_tool.py
Unit tests for autodna/tools/dogfood.py
"""


from autodna.tools.dogfood import (
    compare_reports,
    count_memory_facts,
    evaluate_gates,
    parse_report,
    parse_task_queue,
    write_report,
)


def test_count_memory_facts_counts_lines(tmp_path):
    mem_file = tmp_path / "MEMORY.md"
    mem_file.write_text("# MEMORY\n- Fact 1\n- Fact 2\n\n- Fact 3\n", encoding="utf-8")

    assert count_memory_facts(mem_file) == 3


def test_count_memory_facts_missing_file(tmp_path):
    missing = tmp_path / "MISSING.md"
    assert count_memory_facts(missing) is None


def test_parse_task_queue_counts_sections(tmp_path):
    queue_file = tmp_path / "TASK_QUEUE.md"
    queue_file.write_text(
        "# TASK QUEUE\n"
        "# LAST_SYNC: 2026-03-15T01:46:44Z\n\n"
        "## IN PROGRESS\n"
        "- [ ] TASK_ONE: Do thing\n\n"
        "## BACKLOG\n"
        "- [ ] TASK_TWO: Do later\n"
        "- [ ] TASK_THREE: Do later\n\n"
        "## DONE\n"
        "- [x] TASK_FOUR: Done\n",
        encoding="utf-8",
    )

    data = parse_task_queue(queue_file)
    assert data["last_sync"] == "2026-03-15T01:46:44Z"
    assert data["counts"]["in_progress"] == 1
    assert data["counts"]["backlog"] == 2
    assert data["counts"]["done"] == 1


def test_write_report_creates_file(tmp_path):
    report = "# Dogfood Report\n"
    out_dir = tmp_path / "reports"

    output_path = write_report(report, out_dir, label="baseline", timestamp="2026-03-15T00:00:00Z")

    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == report
    assert output_path.parent == out_dir


def test_parse_report_extracts_metrics(tmp_path):
    report_path = tmp_path / "report.md"
    report_path.write_text(
        "# Dogfood Report\n"
        "- Timestamp: 2026-03-15T00:00:00Z\n"
        "- Label: baseline\n"
        "- Repo: /tmp/repo\n"
        "- Notes: test\n"
        "\n"
        "## Signals\n"
        "- Memory facts: 12\n"
        "- Task counts: in_progress=1, backlog=3, done=4\n"
        "- Task queue last_sync: 2026-03-15T01:00:00Z\n"
        "\n"
        "## Benchmark\n"
        "- Files scanned: 10\n"
        "- Total lines: 200\n"
        "- Total bytes: 3000\n"
        "- Estimated tokens: 750\n",
        encoding="utf-8",
    )

    metrics = parse_report(report_path)
    assert metrics["memory_facts"] == 12
    assert metrics["in_progress"] == 1
    assert metrics["backlog"] == 3
    assert metrics["done"] == 4
    assert metrics["estimated_tokens"] == 750


def test_compare_reports_and_gates(tmp_path):
    baseline_path = tmp_path / "base.md"
    after_path = tmp_path / "after.md"

    baseline_path.write_text(
        "# Dogfood Report\n"
        "- Memory facts: 10\n"
        "- Task counts: in_progress=1, backlog=2, done=3\n",
        encoding="utf-8",
    )
    after_path.write_text(
        "# Dogfood Report\n"
        "- Memory facts: 12\n"
        "- Task counts: in_progress=2, backlog=3, done=5\n",
        encoding="utf-8",
    )

    baseline = parse_report(baseline_path)
    after = parse_report(after_path)
    deltas = compare_reports(baseline, after)

    assert deltas["memory_facts_delta"] == 2
    assert deltas["backlog_delta"] == 1

    failures = evaluate_gates(after, deltas, ["memory_facts<=100", "backlog_delta<=0"])
    assert any("backlog_delta<=0" in failure for failure in failures)
