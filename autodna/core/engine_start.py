import os
import subprocess
import time
import sys
import pathlib
import shutil
import json

GEMINI_PLATFORMS = {"GEMINI", "GEMINI_CLI", "GEMINI-CLI", "ANTIGRAVITY"}
DIRTY_POLICY_DEFAULT = "commit"
DIRTY_POLICY_KEEP = "keep"
DIRTY_POLICY_STASH = "stash"
DIRTY_POLICY_COMMIT = "commit"


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


def _bool_env(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes"}


def _load_task_db(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    tasks = data.get("tasks", [])
    return tasks if isinstance(tasks, list) else []


def _assigned_task_ids(agent_name: str, status: str = "in_progress") -> list[int]:
    tasks = _load_task_db(pathlib.Path("agent/TASK_QUEUE.json"))
    ids = []
    for task in tasks:
        if task.get("assigned_to") != agent_name:
            continue
        if task.get("status") != status:
            continue
        task_id = task.get("id")
        if isinstance(task_id, int):
            ids.append(task_id)
    return sorted(ids)


def _run_git(args: list[str], cwd: pathlib.Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )


def _ensure_safe_directory(path: pathlib.Path) -> None:
    if _bool_env("AUTODNA_WORKTREE_SAFE_DIRECTORY", "1") or _bool_env("AUTODNA_GIT_SAFE_DIRECTORY", "0"):
        _run_git(["config", "--global", "--add", "safe.directory", str(path.resolve())])


def _stash_worktree(path: pathlib.Path) -> bool:
    message = f"autodna-worktree-{path.name}-{int(time.time())}"
    result = _run_git(["stash", "push", "-u", "-m", message], cwd=path)
    if result.returncode != 0:
        print(f"âš ï¸  Failed to stash changes in {path}.")
        if result.stdout:
            print(result.stdout.strip()[-1000:])
        if result.stderr:
            print(result.stderr.strip()[-1000:])
        return False
    return True


def _commit_worktree(path: pathlib.Path) -> bool:
    add = _run_git(["add", "-A"], cwd=path)
    if add.returncode != 0:
        print(f"âš ï¸  Failed to stage changes in {path}.")
        return False
    diff = _run_git(["diff", "--cached", "--quiet"], cwd=path)
    if diff.returncode == 0:
        return True
    message = f"chore: snapshot worktree {path.name}"
    commit = _run_git(["commit", "-m", message], cwd=path)
    if commit.returncode != 0:
        print(f"âš ï¸  Failed to commit changes in {path}.")
        if commit.stdout:
            print(commit.stdout.strip()[-1000:])
        if commit.stderr:
            print(commit.stderr.strip()[-1000:])
        return False
    return True


def _handle_dirty_worktree(path: pathlib.Path, policy: str | None) -> bool:
    normalized = (policy or DIRTY_POLICY_DEFAULT).strip().lower()
    if normalized == DIRTY_POLICY_KEEP:
        return True
    if normalized not in {DIRTY_POLICY_STASH, DIRTY_POLICY_COMMIT}:
        print(f"âš ï¸  Unknown dirty policy '{policy}'. Keeping changes.")
        return True

    _ensure_safe_directory(path)
    if normalized == DIRTY_POLICY_STASH:
        if _stash_worktree(path):
            return True
        _ensure_safe_directory(path)
        return _stash_worktree(path)

    if _commit_worktree(path):
        return True
    _ensure_safe_directory(path)
    if _commit_worktree(path):
        return True
    print(f"âš ï¸  Failed to commit changes in {path}. Falling back to stash.")
    if _stash_worktree(path):
        return True
    _ensure_safe_directory(path)
    return _stash_worktree(path)


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


def _worktree_has_changes(path: pathlib.Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _remove_worktree(name: str) -> bool:
    result = subprocess.run(
        ["git", "worktree", "remove", name],
        shell=False,
    )
    return result.returncode == 0


def setup_worktree(name):
    worktree_path = pathlib.Path(name)
    if worktree_path.exists():
        if _is_worktree_dir(worktree_path):
            branch_name = f"autodna-{name}"
            if not _branch_exists(branch_name):
                print(f"âš ï¸  Worktree {name} exists without branch {branch_name}. Resolve manually.")
                sys.exit(1)
            resume_enabled = True
            resume_existing = False
            if not _branch_is_ancestor(branch_name, "HEAD"):
                if resume_enabled:
                    print(
                        f"âš ï¸  Branch {branch_name} has unmerged commits. "
                        "Resuming existing worktree."
                    )
                    resume_existing = True
                else:
                    print(
                        f"âš ï¸  Branch {branch_name} has unmerged commits. "
                        "Resolve manually before recreating worktree."
                    )
                    sys.exit(1)
            if _worktree_has_changes(worktree_path):
                if resume_enabled:
                    dirty_policy = os.environ.get("AUTODNA_WORKTREE_DIRTY_POLICY", DIRTY_POLICY_DEFAULT)
                    handled = _handle_dirty_worktree(worktree_path, dirty_policy)
                    if not handled:
                        print(f"âš ï¸  Worktree {name} has uncommitted changes. Proceeding without cleanup.")
                    else:
                        print(f"âš ï¸  Worktree {name} has uncommitted changes. Resuming existing worktree.")
                    resume_existing = True
                else:
                    print(f"âš ï¸  Worktree {name} has uncommitted changes. Resolve manually.")
                    sys.exit(1)
            if not resume_existing:
                print(f"ðŸ”„ Refreshing worktree {name} to latest HEAD.")
                if not _remove_worktree(name):
                    print(f"âŒ Error: Failed to remove worktree '{name}'.")
                    sys.exit(1)
        else:
            print(f"âš ï¸  Found non-worktree folder {name}. Removing to recreate worktree.")
            shutil.rmtree(worktree_path, ignore_errors=True)

    if not worktree_path.exists():
        print(f"ðŸ“‚ Creating worktree: {name}...")
        branch_name = f"autodna-{name}"
        if _branch_exists(branch_name):
            if not _branch_is_ancestor(branch_name, "HEAD"):
                print(
                    f"âš ï¸  Branch {branch_name} has unmerged commits. "
                    "Using existing branch state."
                )
            else:
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


def build_manager_mission(assignments: dict[str, list[int]] | None = None) -> str:
    cmd = _task_cli_hint()
    assignments = assignments or {}
    worker_1 = assignments.get("worker-1", [])
    worker_2 = assignments.get("worker-2", [])
    if worker_1 or worker_2:
        resume_hint = (
            "Resume in-progress work before assigning new tasks: "
            f"worker-1 {worker_1 or 'none'}, worker-2 {worker_2 or 'none'}."
        )
    else:
        resume_hint = "Resume any in-progress work before assigning new tasks."
    return (
        "Manager Mode: You are the TPM. Run "
        f"`{cmd} tasks list` (or `autodna tasks list` if installed) to see tasks. "
        f"{resume_hint} Tell worker-1 or worker-2 to claim specific task IDs. "
        "Before merging, rebase on the base branch, run tests, and then merge via "
        "`python tools/git_ops.py <TASK_ID> merge <pr_url>` to avoid conflicts."
    )


def build_worker_mission(label: str, folder: str, resume_ids: list[int] | None = None) -> str:
    cmd = _task_cli_hint()
    resume_ids = resume_ids or []
    if resume_ids:
        resume_hint = f"Resume assigned in-progress tasks first: {', '.join(str(i) for i in resume_ids)}. "
    else:
        resume_hint = "If you have in-progress tasks assigned to you, resume them before claiming new work. "
    return (
        f"{label}: Run `{cmd} tasks list --status pending` (or `autodna tasks list --status pending` if installed) "
        "to see your queue. "
        f"{resume_hint}"
        f"Claim tasks via `{cmd} tasks claim <id> {folder}` (or `autodna tasks claim <id> {folder}`). "
        f"Complete via `{cmd} tasks complete <id>` (or `autodna tasks complete <id>`). "
        "Before pushing, rebase on the base branch and run tests; prefer "
        "`python tools/git_ops.py <TASK_ID> commit` to auto-rebase/test. "
        f"Stay in {folder} folder."
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

    assignments = {
        "worker-1": _assigned_task_ids("worker-1"),
        "worker-2": _assigned_task_ids("worker-2"),
    }

    # 3. Launch Manager (Orchestrator)
    print(f"ðŸš€ Launching Manager {'(Headless)' if headless else '(Blue)'}...")
    log_m = launch_agent(".", build_manager_mission(assignments), "0B", headless=headless)

    time.sleep(3)

    # 4. Launch Workers
    print(f"ðŸš€ Launching Worker 1 {'(Headless)' if headless else '(Green)'}...")
    log_1 = launch_agent(
        "worker-1",
        build_worker_mission("Worker-1", "worker-1", assignments.get("worker-1")),
        "0A",
        headless=headless,
    )

    time.sleep(3)

    print(f"ðŸš€ Launching Worker 2 {'(Headless)' if headless else '(Yellow)'}...")
    log_2 = launch_agent(
        "worker-2",
        build_worker_mission("Worker-2", "worker-2", assignments.get("worker-2")),
        "0E",
        headless=headless,
    )

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
