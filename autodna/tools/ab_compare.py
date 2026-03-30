import argparse
import os
import subprocess
import shutil
import sys
from pathlib import Path
from datetime import datetime, timezone

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from autodna.tools.experiment import run_task, calculate_metrics

def setup_worktree(path: Path, branch: str = None):
    """Sets up a git worktree at the given path."""
    if path.exists():
        shutil.rmtree(path)
    
    cmd = ["git", "worktree", "add", str(path)]
    if branch:
        cmd.append(branch)
    else:
        # Create a temp branch from current HEAD
        temp_branch = f"autodna-ab-{path.name}"
        subprocess.run(["git", "branch", "-D", temp_branch], check=False, capture_output=True)
        cmd.extend(["-b", temp_branch])
        
    subprocess.run(cmd, check=True, capture_output=True)

def cleanup_worktree(path: Path):
    """Cleans up a git worktree."""
    subprocess.run(["git", "worktree", "remove", str(path), "--force"], check=False, capture_output=True)
    if path.exists():
        shutil.rmtree(path)

def main():
    parser = argparse.ArgumentParser(description="Parallel A/B Worktree Comparator")
    parser.add_argument("--task-cmd", required=True, help="Command to run in both worktrees")
    parser.add_argument("--artifact-pattern", help="Optional glob for artifact files")
    parser.add_argument("--challenger-file", required=True, help="Code file to overwrite in challenger worktree")
    parser.add_argument("--challenger-source", required=True, help="Source of the new code")
    parser.add_argument("--assertion", action="append", default=[], help="Assertions to check")
    
    args = parser.parse_args()
    root = Path.cwd()
    base_dir = root / "worker-baseline"
    chall_dir = root / "worker-challenger"
    
    print(f"--- ⚖️ A/B Comparison: {args.challenger_file} ---")
    
    try:
        # 1. Setup Worktrees
        print("[1/4] Setting up worktrees...")
        setup_worktree(base_dir)
        setup_worktree(chall_dir)
        
        # 2. Apply Challenger Delta
        print(f"[2/4] Applying challenger change to {chall_dir}/{args.challenger_file}...")
        source_code = Path(args.challenger_source).read_text(encoding="utf-8")
        (chall_dir / args.challenger_file).write_text(source_code, encoding="utf-8")
        
        # 3. Parallel Run
        print("[3/4] Running tasks in parallel...")
        # Note: True parallel requires threading/multiprocessing, but worktree isolation is the key.
        # We run them sequentially for stability in this demo environment.
        
        print("  -> Running Baseline...")
        os.chdir(base_dir)
        ok_b, out_base, err_b, dur_b = run_task(args.task_cmd.split())
        
        print("  -> Running Challenger...")
        os.chdir(chall_dir)
        ok_c, out_chall, err_c, dur_c = run_task(args.task_cmd.split())
        
        # Return to root
        os.chdir(root)
        
        # 4. Compare Metrics
        print("[4/4] Comparing results...")
        
        # Find artifacts in worktrees
        art_b = None
        if args.artifact_pattern:
            arts = sorted(list(base_dir.glob(args.artifact_pattern)), key=lambda p: p.stat().st_mtime, reverse=True)
            if arts: art_b = arts[0]
            
        art_c = None
        if args.artifact_pattern:
            arts = sorted(list(chall_dir.glob(args.artifact_pattern)), key=lambda p: p.stat().st_mtime, reverse=True)
            if arts: art_c = arts[0]
            
        metrics_b = calculate_metrics(art_b, out_base, args.assertion)
        metrics_c = calculate_metrics(art_c, out_chall, args.assertion)
        
        print("\nSUMMARY:")
        print(f"  Baseline   | Score: {metrics_b['assertion_score']}% | Size: {metrics_b['size']} | Time: {dur_base:.2f}s")
        print(f"  Challenger | Score: {metrics_c['assertion_score']}% | Size: {metrics_c['size']} | Time: {dur_chall:.2f}s")
        
        if metrics_c['assertion_score'] >= metrics_b['assertion_score'] and metrics_c['size'] > 0:
            print("\n✅ WINNER: CHALLENGER")
        else:
            print("\n❌ WINNER: BASELINE (Challenger failed to improve score or produce output)")
            
    finally:
        print("\nCleaning up...")
        cleanup_worktree(base_dir)
        cleanup_worktree(chall_dir)

if __name__ == "__main__":
    main()
