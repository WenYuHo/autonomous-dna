import argparse
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from autodna.tools import dogfood


def ensure_clean_working_tree() -> None:
    result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if result.stdout.strip():
        print("Working tree is not clean. Commit or stash changes before running improve.")
        print(result.stdout)
        sys.exit(1)


def run_command(cmd, timeout: int, shell: bool) -> tuple[bool, str, str]:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=shell)
    return result.returncode == 0, result.stdout or "", result.stderr or ""


def parse_command(cmd_str: str, shell: bool):
    if shell:
        return cmd_str
    return shlex.split(cmd_str, posix=(os.name != "nt"))


def generate_report(label: str, notes: str, include_benchmark: bool, target_dir: str, out_dir: str) -> Path:
    repo_root = Path(".").resolve()
    memory_path = Path("agent/MEMORY.md")
    queue_path = Path("agent/TASK_QUEUE.md")

    memory_facts = dogfood.count_memory_facts(memory_path)
    task_snapshot = dogfood.parse_task_queue(queue_path)
    benchmark = None
    if include_benchmark:
        benchmark = dogfood.scan_text_tree(Path(target_dir).resolve())

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = dogfood.build_report(
        label=label,
        timestamp=timestamp,
        repo_root=repo_root,
        notes=notes,
        memory_facts=memory_facts,
        task_snapshot=task_snapshot,
        benchmark=benchmark,
    )
    return dogfood.write_report(report, Path(out_dir), label, timestamp)


def compare_and_gate(
    baseline_path: Path,
    after_path: Path,
    gates: list[str],
    use_default_gates: bool,
) -> tuple[list[str], str]:
    baseline = dogfood.parse_report(baseline_path)
    after = dogfood.parse_report(after_path)
    deltas = dogfood.compare_reports(baseline, after)
    effective_gates = list(gates)
    if use_default_gates:
        effective_gates = dogfood.DEFAULT_GATES + effective_gates
    failures = dogfood.evaluate_gates(after, deltas, effective_gates)
    summary = dogfood.format_compare_summary(
        baseline_path=baseline_path,
        after_path=after_path,
        baseline=baseline,
        after=after,
        deltas=deltas,
        gates=effective_gates,
        failures=failures,
    )
    return failures, summary


def revert_changes() -> None:
    subprocess.run(["git", "restore", "."], check=False)
    subprocess.run(
        [
            "git",
            "clean",
            "-fd",
            "--exclude=agent/traces",
            "--exclude=agent/reports",
            "--exclude=agent/dogfood_reports",
            "--exclude=agent/skills/auto_generated",
        ],
        check=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous DNA Improve Command (gated apply/revert)")
    parser.add_argument("--apply-cmd", action="append", default=[], help="Command to apply improvements (repeatable)")
    parser.add_argument("--apply-shell", action="store_true", help="Run apply commands through the shell")
    parser.add_argument("--apply-timeout", type=int, default=900, help="Timeout per apply command (seconds)")
    parser.add_argument("--test-cmd", default="python -m pytest tests/ -v", help="Test command to run")
    parser.add_argument("--test-timeout", type=int, default=1800, help="Timeout for tests (seconds)")
    parser.add_argument("--skip-tests", action="store_true", help="Skip tests")
    parser.add_argument("--baseline-label", default="baseline", help="Label for baseline report")
    parser.add_argument("--after-label", default="after", help="Label for after report")
    parser.add_argument("--notes", default="", help="Notes to include in reports")
    parser.add_argument("--include-benchmark", action="store_true", help="Include repo size scan in reports")
    parser.add_argument("--target-dir", default=".", help="Target directory for benchmark scanning")
    parser.add_argument("--out-dir", default="agent/dogfood_reports", help="Directory for dogfood reports")
    parser.add_argument("--gate", action="append", default=[], help="Gate expression (repeatable)")
    parser.add_argument("--no-default-gates", action="store_true", help="Disable default gates")
    parser.add_argument("--allow-dirty", action="store_true", help="Allow dirty working tree")
    parser.add_argument("--no-revert", action="store_true", help="Do not revert on failure")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without running commands")

    args = parser.parse_args()

    if not args.allow_dirty:
        ensure_clean_working_tree()

    if args.dry_run:
        print("[DRY RUN] Would generate baseline/after dogfood reports, apply commands, run tests, and gate.")
        sys.exit(0)

    if not args.apply_cmd:
        print("No apply commands provided. Use --apply-cmd to specify improvement actions.")
        sys.exit(1)

    baseline_path = generate_report(
        label=args.baseline_label,
        notes=args.notes,
        include_benchmark=args.include_benchmark,
        target_dir=args.target_dir,
        out_dir=args.out_dir,
    )
    print(f"Baseline report: {baseline_path}")

    for cmd_str in args.apply_cmd:
        cmd = parse_command(cmd_str, shell=args.apply_shell)
        ok, out, err = run_command(cmd, timeout=args.apply_timeout, shell=args.apply_shell)
        if not ok:
            print("Apply command failed:")
            if out:
                print(out[-2000:])
            if err:
                print(err[-2000:])
            if not args.no_revert:
                revert_changes()
            sys.exit(1)

    if not args.skip_tests:
        test_cmd = parse_command(args.test_cmd, shell=args.apply_shell)
        ok, out, err = run_command(test_cmd, timeout=args.test_timeout, shell=args.apply_shell)
        if not ok:
            print("Tests failed:")
            if out:
                print(out[-2000:])
            if err:
                print(err[-2000:])
            if not args.no_revert:
                revert_changes()
            sys.exit(1)

    after_path = generate_report(
        label=args.after_label,
        notes=args.notes,
        include_benchmark=args.include_benchmark,
        target_dir=args.target_dir,
        out_dir=args.out_dir,
    )
    print(f"After report: {after_path}")

    failures, summary = compare_and_gate(
        baseline_path=baseline_path,
        after_path=after_path,
        gates=args.gate,
        use_default_gates=not args.no_default_gates,
    )
    print(summary)

    if failures:
        print("Gate failures detected.")
        if not args.no_revert:
            revert_changes()
        sys.exit(2)

    print("Improve run accepted. Gates passed.")


if __name__ == "__main__":
    main()
