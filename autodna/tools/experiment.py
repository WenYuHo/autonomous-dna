import sys
import argparse
import subprocess
import time
import os
import shutil
import re
from pathlib import Path
from datetime import datetime, timezone

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from autodna.tools.io_utils import read_text_fallback
from autodna.tools.assertion_evaluator import AssertionEvaluator

def run_task(cmd: list[str], timeout: int = 300) -> tuple[bool, str, str, float]:
    start = time.perf_counter()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", shell=True, timeout=timeout)
        duration = time.perf_counter() - start
        return result.returncode == 0, result.stdout or "", result.stderr or "", duration
    except subprocess.TimeoutExpired:
        return False, "", "TIMEOUT", timeout

def calculate_metrics(artifact_path: Path = None, stdout: str = "", assertions: list[str] = None) -> dict:
    metrics = {"exists": False, "size": 0, "token_estimate": 0, "signal_score": 0, "assertion_score": 100}
    
    # 1. Parse from stdout
    if stdout:
        matches = re.findall(r"([a-zA-Z_]+):\s*([\d.]+)", stdout)
        for key, val in matches:
            try:
                metrics[key.lower()] = float(val)
            except ValueError:
                continue

    # 2. Parse from file
    content = ""
    if artifact_path and artifact_path.exists():
        metrics["exists"] = True
        content = read_text_fallback(artifact_path)
        metrics["size"] = len(content)
        metrics["token_estimate"] = metrics["size"] // 4
        
        if "signal_score" not in metrics:
            unique_domains = len(set(re.findall(r"## Source: https?://([^/]+)", content)))
            metrics["signal_score"] = round(unique_domains * 2.0, 2)
            
    # 3. Evaluate Assertions (Claude Pattern)
    if assertions:
        target_content = (content + "\n" + stdout).strip()
        eval_result = AssertionEvaluator.evaluate(target_content, assertions)
        metrics["assertion_score"] = eval_result["score"]
        metrics["assertions_passed"] = eval_result["passed_count"]
        metrics["assertions_total"] = eval_result["total_count"]
            
    return metrics

def revert_changes():
    subprocess.run(["git", "restore", "."], check=False)

def main():
    parser = argparse.ArgumentParser(description="Autonomous DNA Experiment Runner (Claude-Integrated)")
    parser.add_argument("--target", required=True, help="File path to the tool code")
    parser.add_argument("--task-cmd", required=True, help="Command to run the task")
    parser.add_argument("--artifact-pattern", help="Optional glob pattern for artifact file")
    parser.add_argument("--delta-file", help="Path to the new version of target")
    parser.add_argument("--timeout", type=int, default=300, help="Time budget")
    parser.add_argument("--no-revert", action="store_true", help="Keep changes on failure")
    parser.add_argument("--gate", action="append", default=[], help="Gate: 'metric>=baseline*1.1'")
    parser.add_argument("--assertion", action="append", default=[], help="Assertion: 'contains: pattern'")
    
    args = parser.parse_args()
    target_path = Path(args.target)
    
    print(f"--- 🧪 Experiment: {args.target} ---")
    
    # 1. BASELINE
    print("[STEP 1] Running Baseline...")
    ok, out, err, dur = run_task(args.task_cmd.split(), timeout=args.timeout)
    artifact = None
    if args.artifact_pattern:
        arts = sorted(list(Path(".").glob(args.artifact_pattern)), key=lambda p: p.stat().st_mtime, reverse=True)
        if arts: artifact = arts[0]
        
    baseline_metrics = calculate_metrics(artifact, out, args.assertion)
    print(f"Baseline Metrics: {baseline_metrics}")
    
    # 2. APPLY DELTA
    if not args.delta_file:
        print("[STEP 2] No delta provided. Exit.")
        sys.exit(0)
        
    print(f"[STEP 2] Applying Delta from {args.delta_file}...")
    backup = target_path.with_suffix(".py.bak")
    shutil.copy(target_path, backup)
    target_path.write_text(Path(args.delta_file).read_text(encoding="utf-8"), encoding="utf-8")
    
    # 3. EXPERIMENT
    print("[STEP 3] Running Experiment...")
    ok, out, err, dur = run_task(args.task_cmd.split(), timeout=args.timeout)
    artifact = None
    if args.artifact_pattern:
        arts = sorted(list(Path(".").glob(args.artifact_pattern)), key=lambda p: p.stat().st_mtime, reverse=True)
        if arts: artifact = arts[0]
        
    exp_metrics = calculate_metrics(artifact, out, args.assertion)
    print(f"Experiment Metrics: {exp_metrics}")
    
    # 4. EVALUATION & GATING
    failures = []
    
    # Check Assertions (Mandatory Fail if score < 100)
    if exp_metrics.get("assertion_score", 100) < 100:
        failures.append(f"Assertions Failed ({exp_metrics['assertions_passed']}/{exp_metrics['assertions_total']})")

    # Check Gates
    for gate in args.gate:
        m = re.match(r"([a-z_]+)\s*([<>!=]=?)\s*([\w\.*]+)", gate)
        if m:
            metric, op, thresh_str = m.groups()
            val = exp_metrics.get(metric, 0)
            base = baseline_metrics.get(metric, 0)
            thresh = base * float(thresh_str.split("*")[1]) if "*" in thresh_str else float(thresh_str)
            if not eval(f"{val} {op} {thresh}"):
                failures.append(f"Gate Fail: {gate} (Actual: {val}, Expected: {op}{thresh})")
    
    if failures:
        print(f"\n❌ GATES/ASSERTIONS FAILED:")
        for f in failures: print(f"  - {f}")
        if not args.no_revert:
            print("\n[REVERTING] Restoring baseline...")
            revert_changes()
        sys.exit(2)
    
    print("\n✅ SUCCESS! All assertions and gates passed.")
    if backup.exists(): backup.unlink()

if __name__ == "__main__":
    main()
