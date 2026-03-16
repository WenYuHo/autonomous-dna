import os
import subprocess
import time
import sys
import pathlib
import shutil

GEMINI_PLATFORMS = {"GEMINI", "GEMINI_CLI", "GEMINI-CLI", "ANTIGRAVITY"}


def resolve_platform() -> str:
    env_platform = os.environ.get("AUTODNA_PLATFORM")
    if env_platform:
        return env_platform
    active = pathlib.Path("platform/ACTIVE")
    if active.exists():
        value = active.read_text().strip()
        if value:
            return value
    return "GEMINI"


def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def setup_junction(target_dir, folder_name, force=False):
    """Creates a Windows Junction to share the environment."""
    root_folder = os.path.join(os.getcwd(), folder_name)
    target_folder = os.path.join(target_dir, folder_name)

    if force and os.path.exists(target_folder):
        shutil.rmtree(target_folder, ignore_errors=True)

    if os.path.exists(root_folder) and not os.path.exists(target_folder):
        print(f"ðŸ”— Linking {folder_name} to {target_dir}...")
        # /J creates a directory junction on Windows
        subprocess.run(f'mklink /J "{target_folder}" "{root_folder}"', shell=True)


def _is_worktree_dir(path: pathlib.Path) -> bool:
    git_path = path / ".git"
    return git_path.is_file() or git_path.is_dir()


def _branch_exists(branch_name: str) -> bool:
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"],
        shell=False,
    )
    return result.returncode == 0


def _branch_is_ancestor(branch_name: str, head_ref: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", branch_name, head_ref],
        shell=False,
    )
    return result.returncode == 0


def _update_branch_to_head(branch_name: str, head_ref: str) -> bool:
    result = subprocess.run(
        ["git", "branch", "-f", branch_name, head_ref],
        shell=False,
    )
    return result.returncode == 0


def setup_worktree(name):
    worktree_path = pathlib.Path(name)
    if worktree_path.exists() and not _is_worktree_dir(worktree_path):
        print(f"âš ï¸  Found non-worktree folder {name}. Removing to recreate worktree.")
        shutil.rmtree(worktree_path, ignore_errors=True)

    if not worktree_path.exists():
        print(f"ðŸ“‚ Creating worktree: {name}...")
        branch_name = f"autodna-{name}"
        if _branch_exists(branch_name):
            if not _branch_is_ancestor(branch_name, "HEAD"):
                print(
                    f"âš ï¸  Branch {branch_name} has unmerged commits. "
                    "Resolve manually before recreating worktree."
                )
                sys.exit(1)
            if not _update_branch_to_head(branch_name, "HEAD"):
                print(f"âŒ Error: Failed to fast-forward {branch_name} to HEAD.")
                sys.exit(1)
            cmd = ["git", "worktree", "add", name, branch_name]
        else:
            cmd = ["git", "worktree", "add", name, "-b", branch_name]
        res = subprocess.run(cmd, shell=False)
        if res.returncode != 0:
            print(f"âŒ Error: Failed to create worktree '{name}'. Check git status (e.g., commit changes first).")
            sys.exit(1)

    # Share the environments to save RAM/Disk
    setup_junction(name, ".venv")
    setup_junction(name, "node_modules")
    setup_junction(name, "models") # Crucial for 2070 Super: share the heavy model files
    setup_junction(name, "agent", force=True)  # Share TASK_QUEUE/MEMORY/traces across worktrees


def _task_cli_hint() -> str:
    return "python -m autodna.cli"


def build_manager_mission() -> str:
    cmd = _task_cli_hint()
    return (
        "Manager Mode: You are the TPM. Run "
        f"`{cmd} tasks list` (or `autodna tasks list` if installed) to see tasks. "
        "Tell worker-1 or worker-2 to claim specific task IDs. Merge branches when done."
    )


def build_worker_mission(label: str, folder: str) -> str:
    cmd = _task_cli_hint()
    return (
        f"{label}: Run `{cmd} tasks list --status pending` (or `autodna tasks list --status pending` if installed) "
        "to see your queue. "
        f"Claim tasks via `{cmd} tasks claim <id> {folder}` (or `autodna tasks claim <id> {folder}`). "
        f"Complete via `{cmd} tasks complete <id>` (or `autodna tasks complete <id>`). Stay in {folder} folder."
    )


def launch_agent(name, mission, color="0A", headless=False):
    # Avoid quotes and newlines in the mission string
    safe_mission = mission.replace('"', "'").replace("\n", " ").strip()
    gpu_instruction = " [GPU SAFETY: Check agent/GPU.lock before use]"
    full_mission = safe_mission + gpu_instruction

    # We use -p (non-interactive) in headless mode to force the CLI to run the command and exit
    if headless:
        print(f"ðŸ•µï¸  Launching {name} in background (headless)...")
        log_name = "manager.log" if name == "." else f"{name}.log"
        log_path = pathlib.Path.cwd() / "agent" / log_name
        log_file = open(str(log_path), "w", encoding="utf-8")
        # CREATE_NO_WINDOW = 0x08000000
        cmd_list = ["python", "-m", "autodna.core.agent_runner", name, full_mission]
        creation_flags = 0x08000000
        platform_name = resolve_platform().strip().upper()
        if platform_name in GEMINI_PLATFORMS:
            # Allow console attachment for Gemini CLI when running headless.
            creation_flags = 0
        subprocess.Popen(
            cmd_list,
            shell=False,
            cwd=name,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
        )
        return log_path
    else:
        # Standard mode: Open interactive windows
        # Note: We must ensure the command is executed, so we prefix with /c if using cmd
        cmd = f'start "AUTODNA-{name}" cmd /k "color {color} && cd {name} && python -m autodna.core.agent_runner {name} \\"{full_mission}\\""'
        subprocess.run(cmd, shell=True)
        return None


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    print("--- ðŸ§¬ AUTONOMOUS DNA ORCHESTRATOR ---")

    if not os.path.exists(".git"):
        print("âŒ Error: Not a git repository. Please run `git init` and commit first.")
        sys.exit(1)

    headless = "--headless" in sys.argv

    # 1. Clean up stale locks
    if os.path.exists("agent/GPU.lock"):
        os.remove("agent/GPU.lock")
        print("ðŸ”“ Cleared stale GPU lock.")

    # 2. Setup Worktrees & Junctions
    setup_worktree("worker-1")
    setup_worktree("worker-2")

    # 3. Launch Manager (Orchestrator)
    print(f"ðŸš€ Launching Manager {'(Headless)' if headless else '(Blue)'}...")
    log_m = launch_agent(".", build_manager_mission(), "0B", headless=headless)

    time.sleep(3)

    # 4. Launch Workers
    print(f"ðŸš€ Launching Worker 1 {'(Headless)' if headless else '(Green)'}...")
    log_1 = launch_agent("worker-1", build_worker_mission("Worker-1", "worker-1"), "0A", headless=headless)

    time.sleep(3)

    print(f"ðŸš€ Launching Worker 2 {'(Headless)' if headless else '(Yellow)'}...")
    log_2 = launch_agent("worker-2", build_worker_mission("Worker-2", "worker-2"), "0E", headless=headless)

    if headless:
        print("\nâœ… Autonomous DNA is running in background. Streaming logs below... (Press Ctrl+C to exit monitor loop)")
        print("--------------------------------------------------------------------------------")

        # Build file readers
        readers = {
            "MANAGER": open(str(log_m), "r", encoding="utf-8"),
            "WORKER-1": open(str(log_1), "r", encoding="utf-8"),
            "WORKER-2": open(str(log_2), "r", encoding="utf-8")
        }

        try:
            while True:
                for agent_name, f in readers.items():
                    line = f.readline()
                    if line:
                        stripped = line.strip()
                        if stripped:
                            print(f"[{agent_name}] {stripped}")
                time.sleep(0.05)
        except KeyboardInterrupt:
            print("\nðŸ›‘ Exiting live monitor. Autonomous DNA agents are still running in the background!")
    else:
        print("\nâœ… Autonomous DNA is running in interactive mode.")


if __name__ == "__main__":
    main()
