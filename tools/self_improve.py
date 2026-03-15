"""
tools/self_improve.py
Orchestrator for the Autonomous-DNA self-improvement loop.
Allows the agent swarm to work on its own repository autonomously.

Usage:
  python tools/self_improve.py [--dry-run]
"""

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

# Setup basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TASK_QUEUE_FILE = Path("agent/TASK_QUEUE.json")

from typing import Any, Dict, Optional

def require_clean_working_tree():
    """Ensure no uncommitted changes before starting."""
    result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if result.stdout.strip():
        logger.error("Working tree is not clean. Commit or stash changes before running self-improve.")
        print(result.stdout)
        sys.exit(1)

def get_next_task() -> Optional[Dict[str, Any]]:
    """Find the first pending task in TASK_QUEUE.json."""
    if not TASK_QUEUE_FILE.exists():
        logger.error(f"{TASK_QUEUE_FILE} not found.")
        sys.exit(1)
        
    with open(TASK_QUEUE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    for task in data.get("tasks", []):
        if task.get("status") == "pending":
            logger.info(f"Found pending task: {task['id']} - {task['title']}")
            return task
            
    logger.info("No pending tasks found.")
    return None

def update_task_status(task_id: int, new_status: str, notes: Optional[str] = None) -> None:
    """Update task status in TASK_QUEUE.json to prevent infinite loops."""
    with open(TASK_QUEUE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    for task in data.get("tasks", []):
        if task.get("id") == task_id:
            task["status"] = new_status
            if notes:
                task["notes"] = notes
            break
            
    with open(TASK_QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def checkout_branch(branch_name: str) -> None:
    """Check out a new branch or switch if it exists."""
    # Check if branch exists locally
    result = subprocess.run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"])
    if result.returncode == 0:
        logger.info(f"Switching to existing branch: {branch_name}")
        subprocess.run(["git", "checkout", branch_name], check=True)
    else:
        logger.info(f"Creating new branch from main: {branch_name}")
        subprocess.run(["git", "checkout", "main"], check=True)
        subprocess.run(["git", "checkout", "-b", branch_name], check=True)

def run_tests() -> bool:
    """Run the pytest suite to validate changes."""
    logger.info("Running test suite...")
    result = subprocess.run(["python", "-m", "pytest", "tests/"], capture_output=True, text=True)
    
    if result.returncode == 0:
        logger.info("Tests passed successfully.")
        return True
    else:
        logger.error(f"Tests failed (exit code {result.returncode})")
        logger.error(result.stdout[-1000:]) # Show last 1000 chars of output
        return False

def run_swarm(task: Dict[str, Any], timeout_seconds=600) -> bool:
    """Spawn the agent swarm and wait for it to finish."""
    logger.info(f"Spawning swarm for task {task['id']} (timeout: {timeout_seconds}s)...")
    
    try:
        # Pass the task ID so the swarm prioritizes it, and run headlessly
        # We also need to set platform/ACTIVE if autodna cli expects it, 
        # but starting autodna CLI via python module is safest cross-platform option
        process = subprocess.Popen(
            ["python", "-m", "autodna.cli", "start", "--headless"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        start_time = time.time()
        
        while True:
            # Check if process ended naturally
            retcode = process.poll()
            if retcode is not None:
                if retcode == 0:
                    logger.info("Swarm completed normally.")
                    return True
                else:
                    logger.error(f"Swarm exited with error code {retcode}")
                    # Output the logs to help debug
                    out, _ = process.communicate()
                    print(out[-2000:] if out else "No output.")
                    return False
                    
            # Check timeout
            if time.time() - start_time > timeout_seconds:
                logger.error(f"Swarm timed out after {timeout_seconds} seconds. Terminating.")
                process.terminate()
                process.wait(timeout=5)
                return False
                
            # Wait a bit before checking again
            time.sleep(5)
            
            # Periodically check TASK_QUEUE.json to see if the task is done, error, etc.
            # (In headless mode the swarm might stay alive listening, depending on implementation)
            with open(TASK_QUEUE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for t in data.get("tasks", []):
                    if t.get("id") == task["id"]:
                        if t.get("status") == "done":
                            logger.info(f"Task marked 'done' in queue! Terminating swarm.")
                            process.terminate()
                            return True
                        elif t.get("status") in ["error", "blocked"]:
                            logger.error(f"Task marked '{t.get('status')}' in queue.")
                            process.terminate()
                            return False
                            
    except Exception as e:
        logger.error(f"Error orchestrating swarm: {e}")
        return False

def commit_changes(task: Dict[str, Any]) -> None:
    """Commit changes to the current branch."""
    msg = f"feat: Auto-complete task {task['id']} - {task['title'][:50]}"
    
    # We purposefully exclude TASK_QUEUE and MEMORY from committing into branches
    # using the .gitignore we set up earlier. Only code changes get pushed.
    
    logger.info("Committing passing changes...")
    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(["git", "commit", "-m", msg], check=True)
    logger.info(f"Changes committed successfully! ({msg})")

def rollback_changes() -> None:
    """Discard uncommitted changes in the working directory."""
    logger.info("Rolling back uncommitted changes...")
    subprocess.run(["git", "restore", "."], check=True)
    subprocess.run(["git", "clean", "-fd", "--exclude=agent/traces", "--exclude=agent/reports"], check=True)
    logger.info("Rollback complete.")

def main():
    parser = argparse.ArgumentParser(description="Autonomous DNA Dogfooding Orchestrator")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without spawning swarm")
    args = parser.parse_args()
    
    logger.info("Starting Autonomous-DNA Self-Improvement Loop...")
    
    if not args.dry_run:
        require_clean_working_tree()
        
    task = get_next_task()
    if not task:
        sys.exit(0)
        
    assert task is not None # Tell type checker it's safe
        
    branch_name = f"chore/self-improve-task-{task['id']}"
    
    if args.dry_run:
        logger.info(f"[DRY RUN] Would check out branch: {branch_name}")
        logger.info(f"[DRY RUN] Would start swarm for task {task['id']}")
        logger.info(f"[DRY RUN] Would run pytest and commit if passed")
        sys.exit(0)
        
    try:
        checkout_branch(branch_name)
        
        success = run_swarm(task)
        
        if success:
            tests_passed = run_tests()
            if tests_passed:
                commit_changes(task)
                update_task_status(task["id"], "done")
                logger.info(f"Task {task['id']} completed successfully. Review branch {branch_name}.")
            else:
                logger.error("Tests failed! Rolling back changes to prevent master corruption.")
                rollback_changes()
                update_task_status(task["id"], "error", "Tests failed after implementation.")
        else:
            logger.error("Swarm failed to complete task.")
            rollback_changes()
            update_task_status(task["id"], "error", "Swarm exited with error or timeout.")
            
        subprocess.run(["git", "checkout", "main"], check=True)
        
    except Exception as e:
        logger.exception("Catastrophic error in self-improve loop:")
        rollback_changes()
        update_task_status(task["id"], "error", f"Self-improve script crashed: {e}")
        subprocess.run(["git", "checkout", "main"], check=True)

if __name__ == "__main__":
    main()
