"""
tools/manage_env.py
Automates creation and reset of the local Autonomous-DNA-Workspace environments.

Usage:
  python tools/manage_env.py reset-lab
  python tools/manage_env.py setup-target
  python tools/manage_env.py setup-all

Assumes the script is run from within the main repository (source) 
which is located at Autonomous-DNA-Workspace/source/.
"""
import sys
import shutil
import subprocess
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def run_cmd(cmd, cwd=None, ignore_errors=False):
    print(f"Running: {cmd}")
    res = subprocess.run(cmd, shell=True, cwd=cwd, text=True, capture_output=True)
    if res.returncode != 0 and not ignore_errors:
        print(f"Error executing {cmd}\n{res.stderr}")
        sys.exit(1)
    return res.returncode, res.stdout, res.stderr

def get_workspace_root():
    # manage_env.py is in Workspace/source/tools
    # return Workspace/
    return Path(__file__).resolve().parent.parent.parent

def get_repo_root():
    return Path(__file__).resolve().parent.parent

def reset_lab():
    ws_root = get_workspace_root()
    repo_root = get_repo_root()
    
    lab_dir = ws_root / "lab"
    origin_dir = ws_root / "lab-origin.git"
    
    print(f"--- Resetting Lab Environment ---")
    print(f"Workspace Root: {ws_root}")
    
    # 1. Clean up old lab and origin
    print("Removing old lab and origin repositories...")
    if lab_dir.exists():
        run_cmd(f'git worktree remove --force "{lab_dir}"', cwd=repo_root, ignore_errors=True)
        # Fallback to shutil if git worktree remove fails
        if lab_dir.exists():
            shutil.rmtree(lab_dir, ignore_errors=True)
            run_cmd(f'git worktree prune', cwd=repo_root, ignore_errors=True)
            
    if origin_dir.exists():
        shutil.rmtree(origin_dir, ignore_errors=True)

    # Re-create just to be safe
    if origin_dir.exists() or lab_dir.exists():
        print("Error: Could not cleanly delete previous directories.")
        sys.exit(1)
        
    origin_dir.mkdir(parents=True, exist_ok=True)
    
    # 2. Recreate origin
    print("Initializing bare repository lab-origin.git...")
    run_cmd('git init --bare', cwd=origin_dir)
    
    # 3. Create lab worktree
    print("Creating lab worktree (branch: lab-agent)...")
    # Delete lab-agent branch if it exists so we can create it fresh
    run_cmd('git branch -D lab-agent', cwd=repo_root, ignore_errors=True)
    
    # Add new worktree checking out a fresh branch 'lab-agent'
    run_cmd(f'git worktree add -b lab-agent "{lab_dir}"', cwd=repo_root)
    
    # 4. Set remote
    print("Setting remote lab-origin for lab...")
    # Add a custom remote URL for the local bare repo so it doesn't overwrite the main 'origin'
    run_cmd(f'git remote remove lab-origin', cwd=lab_dir, ignore_errors=True)
    run_cmd(f'git remote add lab-origin "{origin_dir}"', cwd=lab_dir)
    run_cmd(f'git push --set-upstream lab-origin lab-agent', cwd=lab_dir)
    
    print("Lab environment reset successfully.\n")

def setup_target():
    ws_root = get_workspace_root()
    target_dir = ws_root / "target"
    
    print(f"--- Setting up Target Environment ---")
    if target_dir.exists():
        print(f"Target directory already exists at {target_dir}")
        print("Please remove it if you wish to clone it again.")
        return
        
    print("Cloning main repository into target...")
    run_cmd(f'git clone https://github.com/WenYuHo/Autonomous-DNA.git "{target_dir}"')
    
    print("Checking out codex/lab-target branch...")
    # Try checking out the existing remote branch
    code, out, err = run_cmd(f'git checkout codex/lab-target', cwd=target_dir, ignore_errors=True)
    if code != 0:
        # If it doesn't exist, create it from main
        run_cmd(f'git checkout -b codex/lab-target', cwd=target_dir)
        
    print("Target environment setup successfully.\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/manage_env.py [reset-lab|setup-target|setup-all]")
        sys.exit(1)
        
    cmd = sys.argv[1]
    if cmd == "reset-lab":
        reset_lab()
    elif cmd == "setup-target":
        setup_target()
    elif cmd == "setup-all":
        reset_lab()
        setup_target()
    else:
        print(f"Unknown command: {cmd}")
