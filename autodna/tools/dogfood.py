import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from autodna.tools.benchmark import get_ignore_list, is_text_file
from autodna.tools.io_utils import read_text_fallback

DEFAULT_GATES = [
    "memory_facts<=100",
    "backlog_delta<=0",
]


def count_memory_facts(memory_path: Path) -> Optional[int]:
    if not memory_path.exists():
        return None
    content = read_text_fallback(memory_path)
    return len(re.findall(r"^- ", content, flags=re.MULTILINE))


def parse_task_queue(queue_path: Path) -> dict:
    if not queue_path.exists():
        return {"last_sync": None, "counts": {"in_progress": 0, "backlog": 0, "done": 0}, "exists": False}

    content = queue_path.read_text(encoding="utf-8")
    counts = {"in_progress": 0, "backlog": 0, "done": 0}
    last_sync = None
    section = None

    for line in content.splitlines():
        if line.startswith("# LAST_SYNC:"):
            last_sync = line.split(":", 1)[1].strip()
            continue

        if line.startswith("## "):
            section = line.replace("## ", "").strip().lower()
            continue

        if not line.strip().startswith("- ["):
            continue

        if section == "in progress":
            counts["in_progress"] += 1
        elif section == "backlog":
            counts["backlog"] += 1
        elif section == "done":
            counts["done"] += 1

    return {"last_sync": last_sync, "counts": counts, "exists": True}


def scan_text_tree(target: Path) -> dict:
    ignore_list = get_ignore_list(target)
    total_files = 0
    total_bytes = 0
    total_lines = 0

    for root, dirs, files in target.walk():
        dirs[:] = [d for d in dirs if d not in ignore_list]
        for file in files:
            if file in ignore_list or any(file.endswith(ext) for ext in [".pyc", ".pyo", ".pyd", ".exe", ".dll"]):
                continue

            filepath = Path(root) / file
            if any(ignored in filepath.parts for ignored in ignore_list):
                continue
            if not is_text_file(filepath):
                continue

            try:
                stat = filepath.stat()
                total_bytes += stat.st_size
                total_files += 1
                with open(filepath, "r", encoding="utf-8", errors="ignore") as handle:
                    content = handle.read()
                    total_lines += content.count("\n") + 1
            except Exception:
                continue

    estimated_tokens = int(total_bytes / 4)
    return {
        "files": total_files,
        "bytes": total_bytes,
        "lines": total_lines,
        "estimated_tokens": estimated_tokens,
    }


def build_report(
    label: str,
    timestamp: str,
    repo_root: Path,
    notes: str,
    memory_facts: Optional[int],
    task_snapshot: dict,
    benchmark: Optional[dict],
) -> str:
    lines = []
    lines.append("# Dogfood Report")
    lines.append(f"- Timestamp: {timestamp}")
    lines.append(f"- Label: {label}")
    lines.append(f"- Repo: {repo_root}")
    lines.append(f"- Notes: {notes if notes else '(add hypothesis or expected improvement)'}")
    lines.append("")
    lines.append("## Signals")
    if memory_facts is None:
        lines.append("- Memory facts: MISSING (agent/MEMORY.md)")
    else:
        lines.append(f"- Memory facts: {memory_facts}")
    lines.append(
        "- Task counts: in_progress={in_progress}, backlog={backlog}, done={done}".format(
            **task_snapshot["counts"]
        )
    )
    lines.append(f"- Task queue last_sync: {task_snapshot['last_sync'] or 'UNKNOWN'}")
    lines.append("")
    lines.append("## Checks")
    lines.append(f"- Memory file present: {'PASS' if memory_facts is not None else 'FAIL'}")
    lines.append(f"- Task queue present: {'PASS' if task_snapshot['exists'] else 'FAIL'}")
    if memory_facts is None:
        lines.append("- Memory fact cap (<= 100): FAIL (missing)")
    elif memory_facts <= 100:
        lines.append("- Memory fact cap (<= 100): PASS")
    else:
        lines.append(f"- Memory fact cap (<= 100): WARN ({memory_facts})")
    lines.append(f"- Task queue last_sync set: {'PASS' if task_snapshot['last_sync'] else 'WARN'}")

    if benchmark:
        lines.append("")
        lines.append("## Benchmark")
        lines.append(f"- Files scanned: {benchmark['files']}")
        lines.append(f"- Total lines: {benchmark['lines']}")
        lines.append(f"- Total bytes: {benchmark['bytes']}")
        lines.append(f"- Estimated tokens: {benchmark['estimated_tokens']}")

    lines.append("")
    lines.append("## Evaluation Notes")
    lines.append("- What changed vs baseline?")
    lines.append("- Expected impact (latency, quality, reliability)?")
    lines.append("- Evidence observed (links, logs, diffs)?")
    lines.append("- Next action (keep, revert, iterate)?")
    return "\n".join(lines) + "\n"


def write_report(report: str, out_dir: Path, label: str, timestamp: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_label = re.sub(r"[^a-zA-Z0-9_-]+", "-", label).strip("-") or "run"
    safe_timestamp = timestamp.replace(":", "-")
    filename = f"dogfood_{safe_label}_{safe_timestamp}.md"
    output_path = out_dir / filename
    output_path.write_text(report, encoding="utf-8")
    return output_path


def parse_report(report_path: Path) -> dict:
    if not report_path.exists():
        raise FileNotFoundError(f"Report not found: {report_path}")

    content = report_path.read_text(encoding="utf-8")
    metrics = {}

    timestamp_match = re.search(r"^- Timestamp:\s*(.+)$", content, flags=re.MULTILINE)
    if timestamp_match:
        metrics["timestamp"] = timestamp_match.group(1).strip()

    label_match = re.search(r"^- Label:\s*(.+)$", content, flags=re.MULTILINE)
    if label_match:
        metrics["label"] = label_match.group(1).strip()

    memory_match = re.search(r"^- Memory facts:\s*(\d+)", content, flags=re.MULTILINE)
    if memory_match:
        metrics["memory_facts"] = int(memory_match.group(1))
    else:
        metrics["memory_facts"] = None

    task_match = re.search(
        r"^- Task counts:\s*in_progress=(\d+),\s*backlog=(\d+),\s*done=(\d+)",
        content,
        flags=re.MULTILINE,
    )
    if task_match:
        metrics["in_progress"] = int(task_match.group(1))
        metrics["backlog"] = int(task_match.group(2))
        metrics["done"] = int(task_match.group(3))

    last_sync_match = re.search(r"^- Task queue last_sync:\s*(.+)$", content, flags=re.MULTILINE)
    if last_sync_match:
        metrics["last_sync"] = last_sync_match.group(1).strip()

    bench_files = re.search(r"^- Files scanned:\s*(\d+)", content, flags=re.MULTILINE)
    if bench_files:
        metrics["files_scanned"] = int(bench_files.group(1))
    bench_lines = re.search(r"^- Total lines:\s*(\d+)", content, flags=re.MULTILINE)
    if bench_lines:
        metrics["total_lines"] = int(bench_lines.group(1))
    bench_bytes = re.search(r"^- Total bytes:\s*(\d+)", content, flags=re.MULTILINE)
    if bench_bytes:
        metrics["total_bytes"] = int(bench_bytes.group(1))
    bench_tokens = re.search(r"^- Estimated tokens:\s*(\d+)", content, flags=re.MULTILINE)
    if bench_tokens:
        metrics["estimated_tokens"] = int(bench_tokens.group(1))

    return metrics


def compare_reports(baseline: dict, after: dict) -> dict:
    deltas = {}
    for key in ("memory_facts", "in_progress", "backlog", "done", "estimated_tokens"):
        base_value = baseline.get(key)
        after_value = after.get(key)
        if base_value is None or after_value is None:
            continue
        deltas[f"{key}_delta"] = after_value - base_value
    return deltas


def parse_gate(expr: str) -> tuple[str, str, int]:
    match = re.match(r"^([a-zA-Z_]+)\s*(<=|>=|==|!=|<|>)\s*(-?\d+)$", expr.strip())
    if not match:
        raise ValueError(f"Invalid gate expression: {expr}")
    key, op, value = match.group(1), match.group(2), int(match.group(3))
    return key, op, value


def evaluate_gate(value: int, op: str, threshold: int) -> bool:
    if op == "<=":
        return value <= threshold
    if op == ">=":
        return value >= threshold
    if op == "<":
        return value < threshold
    if op == ">":
        return value > threshold
    if op == "==":
        return value == threshold
    if op == "!=":
        return value != threshold
    raise ValueError(f"Unsupported operator: {op}")


def evaluate_gates(after: dict, deltas: dict, gates: list[str]) -> list[str]:
    failures = []
    for gate in gates:
        key, op, threshold = parse_gate(gate)
        if key.endswith("_delta"):
            value = deltas.get(key)
        else:
            value = after.get(key)
        if value is None:
            failures.append(f"{gate} (missing metric)")
            continue
        if not evaluate_gate(value, op, threshold):
            failures.append(f"{gate} (value={value})")
    return failures


def format_compare_summary(
    baseline_path: Path,
    after_path: Path,
    baseline: dict,
    after: dict,
    deltas: dict,
    gates: list[str],
    failures: list[str],
) -> str:
    lines = []
    lines.append("# Dogfood Comparison")
    lines.append(f"- Baseline: {baseline_path}")
    lines.append(f"- After: {after_path}")
    lines.append("")
    lines.append("## Metrics")
    for key in ("memory_facts", "in_progress", "backlog", "done", "estimated_tokens"):
        if key in baseline and key in after and baseline[key] is not None and after[key] is not None:
            delta = deltas.get(f"{key}_delta")
            delta_str = f"{delta:+}" if delta is not None else "n/a"
            lines.append(f"- {key}: {baseline[key]} -> {after[key]} ({delta_str})")
    lines.append("")
    lines.append("## Gates")
    for gate in gates:
        matched = [f for f in failures if f.startswith(f"{gate} ")]
        lines.append(f"- {gate}: {'FAIL' if matched else 'PASS'}")
    if failures:
        lines.append("")
        lines.append("## Failures")
        for failure in failures:
            lines.append(f"- {failure}")
    return "\n".join(lines) + "\n"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Autonomous DNA Dogfooding Evaluator")
    parser.add_argument("--label", default="run", help="Label for the report filename")
    parser.add_argument("--notes", default="", help="Optional hypothesis or notes")
    parser.add_argument("--out-dir", default="agent/dogfood_reports", help="Output directory for reports")
    parser.add_argument(
        "--include-benchmark",
        action="store_true",
        help="Include repo size scan (files/lines/bytes/token estimate)",
    )
    parser.add_argument("--target-dir", default=".", help="Target directory for benchmark scanning")
    parser.add_argument("--dry-run", action="store_true", help="Print report without writing a file")
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("BASELINE_REPORT", "AFTER_REPORT"),
        help="Compare two dogfood reports and evaluate gates",
    )
    parser.add_argument("--gate", action="append", default=[], help="Gate expression (repeatable)")
    parser.add_argument("--no-default-gates", action="store_true", help="Disable default gates")

    args = parser.parse_args()

    if args.compare:
        baseline_path = Path(args.compare[0])
        after_path = Path(args.compare[1])
        baseline = parse_report(baseline_path)
        after = parse_report(after_path)
        deltas = compare_reports(baseline, after)
        gates = args.gate or []
        if not args.no_default_gates:
            gates = DEFAULT_GATES + gates
        failures = evaluate_gates(after, deltas, gates)
        summary = format_compare_summary(baseline_path, after_path, baseline, after, deltas, gates, failures)
        print(summary)
        sys.exit(2 if failures else 0)

    repo_root = Path(".").resolve()
    memory_path = Path("agent/MEMORY.md")
    queue_path = Path("agent/TASK_QUEUE.md")

    memory_facts = count_memory_facts(memory_path)
    task_snapshot = parse_task_queue(queue_path)

    benchmark = None
    if args.include_benchmark:
        benchmark = scan_text_tree(Path(args.target_dir).resolve())

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = build_report(
        label=args.label,
        timestamp=timestamp,
        repo_root=repo_root,
        notes=args.notes,
        memory_facts=memory_facts,
        task_snapshot=task_snapshot,
        benchmark=benchmark,
    )

    if args.dry_run:
        print(report)
        return

    output_path = write_report(report, Path(args.out_dir), args.label, timestamp)
    print(f"Dogfood report written to: {output_path}")


if __name__ == "__main__":
    main()
