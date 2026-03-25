import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from autodna.core import repo_hooks
from autodna.tools import dogfood, user_dogfood


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


def run_user_dogfood_gate(repo_root: Path, allow_skip: bool, artifact_parent: str | None = None) -> dict:
    if allow_skip:
        return {"ok": True, "skipped": True, "status": "skipped"}
    return user_dogfood.run_user_dogfood_flow(
        repo_root=repo_root,
        artifact_parent=artifact_parent,
    )


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


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _verification_override_hooks(test_cmd: str | None, test_timeout: int, shell: bool) -> list[dict] | None:
    if not test_cmd:
        return None
    return [
        {
            "name": "override_test_command",
            "command": test_cmd,
            "timeout": test_timeout,
            "shell": shell,
        }
    ]


def write_improve_artifact(result: dict, out_dir: Path | str = Path("agent") / "reports") -> Path:
    out_path = Path(out_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    artifact_path = out_path / f"improve_{_now_stamp()}.json"
    artifact_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return artifact_path


def execute_improve(args: argparse.Namespace) -> dict:
    repo_root = Path(".").resolve()
    result = {
        "ok": False,
        "status": "failed",
        "timestamp": _now_stamp(),
        "repo_root": str(repo_root),
        "baseline_report": None,
        "after_report": None,
        "compare_summary": None,
        "gate_failures": [],
        "hook_runs": {},
        "dogfood_result": None,
        "error": None,
        "artifact_path": None,
        "reverted": False,
    }

    def finalize() -> dict:
        artifact_path = write_improve_artifact(result)
        result["artifact_path"] = str(artifact_path)
        return result

    if not args.allow_dirty:
        ensure_clean_working_tree()

    repo_setup = repo_hooks.run_hook_stage(repo_root=repo_root, stage="repo_setup")
    result["hook_runs"]["repo_setup"] = repo_setup
    if not repo_setup.get("ok"):
        result["error"] = "repo setup hooks failed"
        return finalize()

    baseline_path = generate_report(
        label=args.baseline_label,
        notes=args.notes,
        include_benchmark=args.include_benchmark,
        target_dir=args.target_dir,
        out_dir=args.out_dir,
    )
    result["baseline_report"] = str(baseline_path)

    for cmd_str in args.apply_cmd:
        cmd = parse_command(cmd_str, shell=args.apply_shell)
        ok, out, err = run_command(cmd, timeout=args.apply_timeout, shell=args.apply_shell)
        if not ok:
            result["error"] = "apply command failed"
            result["apply_stdout"] = out
            result["apply_stderr"] = err
            if not args.no_revert:
                revert_changes()
                result["reverted"] = True
            return finalize()

    if not args.skip_tests:
        verification_result = repo_hooks.run_hook_stage(
            repo_root=repo_root,
            stage="repo_verification",
            override_hooks=_verification_override_hooks(args.test_cmd, args.test_timeout, args.apply_shell),
        )
        result["hook_runs"]["repo_verification"] = verification_result
        if not verification_result.get("ok"):
            result["error"] = "repo verification hooks failed"
            if not args.no_revert:
                revert_changes()
                result["reverted"] = True
            return finalize()
    else:
        result["hook_runs"]["repo_verification"] = {
            "ok": True,
            "status": "skipped",
            "stage": "repo_verification",
            "hooks": [],
        }

    dogfood_result = run_user_dogfood_gate(
        repo_root,
        allow_skip=args.skip_user_dogfood,
        artifact_parent=Path("agent") / "reports",
    )
    result["dogfood_result"] = dogfood_result
    if not dogfood_result.get("ok"):
        result["error"] = "user dogfood verification failed"
        if not args.no_revert:
            revert_changes()
            result["reverted"] = True
        return finalize()

    after_path = generate_report(
        label=args.after_label,
        notes=args.notes,
        include_benchmark=args.include_benchmark,
        target_dir=args.target_dir,
        out_dir=args.out_dir,
    )
    result["after_report"] = str(after_path)

    failures, summary = compare_and_gate(
        baseline_path=baseline_path,
        after_path=after_path,
        gates=args.gate,
        use_default_gates=not args.no_default_gates,
    )
    result["gate_failures"] = failures
    result["compare_summary"] = summary

    if failures:
        result["error"] = "gate failures detected"
        if not args.no_revert:
            revert_changes()
            result["reverted"] = True
        return finalize()

    result["ok"] = True
    result["status"] = "passed"
    return finalize()


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous DNA Improve Command (gated apply/revert)")
    parser.add_argument("--apply-cmd", action="append", default=[], help="Command to apply improvements (repeatable)")
    parser.add_argument("--apply-shell", action="store_true", help="Run apply commands through the shell")
    parser.add_argument("--apply-timeout", type=int, default=900, help="Timeout per apply command (seconds)")
    parser.add_argument("--test-cmd", help="Override the repo verification command")
    parser.add_argument("--test-timeout", type=int, default=1800, help="Timeout for tests (seconds)")
    parser.add_argument("--skip-tests", action="store_true", help="Skip tests")
    parser.add_argument("--skip-user-dogfood", action="store_true", help="Skip the user dogfood verification flow")
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
        print(
            "[DRY RUN] Would run repo setup hooks, generate baseline/after dogfood reports, "
            "apply commands, run repo verification hooks, run user dogfood, and gate."
        )
        sys.exit(0)

    if not args.apply_cmd:
        print("No apply commands provided. Use --apply-cmd to specify improvement actions.")
        sys.exit(1)

    result = execute_improve(args)
    if result.get("baseline_report"):
        print(f"Baseline report: {result['baseline_report']}")
    if result.get("after_report"):
        print(f"After report: {result['after_report']}")
    for stage_name in ("repo_setup", "repo_verification"):
        stage_result = result["hook_runs"].get(stage_name)
        if stage_result and stage_result.get("manifest_path"):
            print(f"{stage_name} hook manifest: {stage_result['manifest_path']}")
    if result.get("compare_summary"):
        print(result["compare_summary"])
    print(f"Improve artifact: {result['artifact_path']}")

    if result["status"] == "passed":
        print("Improve run accepted. Gates passed.")
        sys.exit(0)

    print(result.get("error") or "Improve run failed.")
    if result.get("dogfood_result", {}).get("artifacts"):
        print("Dogfood artifacts:")
        for label, path in result["dogfood_result"]["artifacts"].items():
            print(f"  {label}: {path}")
    exit_code = 2 if result.get("error") == "gate failures detected" else 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
