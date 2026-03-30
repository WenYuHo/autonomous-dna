"""
tools/git_ops.py
Autonomous git flow: branch, commit, PR, rebase, merge.

Usage:
  python tools/git_ops.py TASK_ID full "commit message"     # do everything
  python tools/git_ops.py TASK_ID init                      # create branch
  python tools/git_ops.py TASK_ID commit "msg"              # stage + commit + push
  python tools/git_ops.py TASK_ID pr                        # open PR
  python tools/git_ops.py TASK_ID merge <pr_url>            # monitor CI + merge
"""

import subprocess
import sys
import os
import shlex
from datetime import datetime, timezone


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"ERROR running {' '.join(cmd)}:\n{result.stderr}")
        sys.exit(1)
    return result


def branch_name(task_id: str) -> str:
    prefix = os.environ.get("AUTODNA_GIT_BRANCH_PREFIX", "feat/")
    return f"{prefix}{task_id.lower()}"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bool_env(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes"}


def _branch_exists(branch_name: str) -> bool:
    local = run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"], check=False)
    if local.returncode == 0:
        return True
    remote = run(["git", "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{branch_name}"], check=False)
    return remote.returncode == 0


def resolve_base_branch() -> str:
    env_branch = os.environ.get("AUTODNA_GIT_BASE_BRANCH") or os.environ.get("AUTODNA_BASE_BRANCH")
    candidates = [env_branch, "main", "dev", "master"]
    for candidate in candidates:
        if not candidate:
            continue
        if _branch_exists(candidate):
            return candidate
    return "main"


def _parse_command(command: str) -> list[str]:
    return shlex.split(command, posix=(os.name != "nt"))


def run_tests() -> None:
    test_cmd = os.environ.get("AUTODNA_GIT_TEST_CMD", "python -m pytest tests/")
    if not test_cmd.strip():
        return
    print(f"Running tests before push: {test_cmd}")
    result = run(_parse_command(test_cmd), check=False)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if result.returncode != 0:
        print("Tests failed. Aborting push.")
        sys.exit(1)


def cmd_init(task_id: str) -> None:
    run(["git", "fetch", "origin"])
    base_branch = resolve_base_branch()
    run(["git", "checkout", base_branch])
    run(["git", "pull", "origin", base_branch])
    branch = branch_name(task_id)
    result = run(["git", "checkout", "-b", branch], check=False)
    if result.returncode != 0:
        # Branch exists — check it out
        run(["git", "checkout", branch])
    print(f"On branch: {branch}")


def cmd_commit(task_id: str, message: str) -> None:
    run(["git", "add", "-A"])
    result = run(["git", "diff", "--cached", "--quiet"], check=False)
    if result.returncode == 0:
        print("Nothing to commit.")
        return
    run_tests()
    run(["git", "commit", "-m", f"{message}\n\nTASK_ID: {task_id}"])
    branch = branch_name(task_id)
    base_branch = resolve_base_branch()
    run(["git", "fetch", "origin"])
    _rebase_with_retry(task_id, base_branch)
    print(f"Committed, rebased, and pushed: {branch}")


def cmd_pr(task_id: str) -> None:
    branch = branch_name(task_id)
    base_branch = resolve_base_branch()

    # Check if behind main
    run(["git", "fetch", "origin"])
    result = run(
        ["git", "rev-list", "--count", f"origin/{base_branch}..{branch}"],
        check=False,
    )
    behind = run(
        ["git", "rev-list", "--count", f"{branch}..origin/{base_branch}"],
        check=False,
    ).stdout.strip()

    if behind and int(behind) > 0:
        print(f"Branch is {behind} commit(s) behind {base_branch}. Rebasing...")
        _rebase_with_retry(task_id, base_branch)

    # Open PR via GitHub CLI
    result = run(
        ["gh", "pr", "create", "--fill", "--base", base_branch, "--head", branch],
        check=False,
    )
    if result.returncode != 0:
        # PR may already exist
        print(f"gh pr create: {result.stderr.strip()}")
    else:
        print(f"PR opened: {result.stdout.strip()}")


def _rebase_with_retry(task_id: str, base_branch: str, max_attempts: int = 3) -> None:
    branch = branch_name(task_id)
    for attempt in range(1, max_attempts + 1):
        result = run(["git", "rebase", f"origin/{base_branch}"], check=False)
        if result.returncode == 0:
            run(["git", "push", "--force-with-lease", "origin", branch])
            return

        # Auto-resolve conflicts
        conflicts = run(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            check=False,
        ).stdout.splitlines()

        TAKE_THEIRS = {".lock", "-lock.json", ".pb.go"}
        SCAFFOLD = {
            "AGENTS.md", "CLAUDE.md", "GEMINI.md",
            ".mcp.json", ".claude/settings.json",
        }

        for f in conflicts:
            if any(f.endswith(ext) for ext in TAKE_THEIRS):
                run(["git", "checkout", "--theirs", f])
            elif any(s in f for s in SCAFFOLD):
                run(["git", "rebase", "--abort"], check=False)
                print(f"STOP: Conflict in scaffold file '{f}'. Cannot auto-resolve.")
                print("Log this in MEMORY.md and notify the human developer.")
                sys.exit(1)
            else:
                run(["git", "checkout", "--ours", f])
            run(["git", "add", f])

        cont = run(["git", "rebase", "--continue"], check=False)
        if cont.returncode == 0:
            run(["git", "push", "--force-with-lease", "origin", branch])
            return

        print(f"Rebase attempt {attempt}/{max_attempts} failed.")

    run(["git", "rebase", "--abort"], check=False)
    print(f"STOP: Rebase failed after {max_attempts} attempts. Notify human.")
    print("Log this in agent/MEMORY.md before stopping.")
    sys.exit(1)


def cmd_merge(task_id: str, pr_url: str) -> None:
    import time
    print(f"Monitoring CI for: {pr_url}")
    for _ in range(30):  # poll up to 30 times (5 min)
        result = run(
            ["gh", "pr", "checks", pr_url, "--json", "state", "--jq", ".[].state"],
            check=False,
        )
        states = result.stdout.splitlines()
        if all(s == "SUCCESS" for s in states if s):
            run(["gh", "pr", "merge", pr_url, "--squash", "--delete-branch"])
            print(f"Merged and branch deleted: {pr_url}")
            return
        if any(s == "FAILURE" for s in states):
            print(f"CI FAILED: {pr_url}")
            print("Log in MEMORY.md and notify human developer.")
            sys.exit(1)
        time.sleep(10)

    print("CI timed out. Check manually.")
    sys.exit(1)


def cmd_full(task_id: str, message: str) -> None:
    cmd_init(task_id)
    cmd_commit(task_id, message)
    cmd_pr(task_id)


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__)
        sys.exit(0)

    task_id = args[0]
    command = args[1]

    if command == "init":
        cmd_init(task_id)
    elif command == "commit":
        cmd_commit(task_id, args[2] if len(args) > 2 else "update")
    elif command == "pr":
        cmd_pr(task_id)
    elif command == "merge":
        cmd_merge(task_id, args[2])
    elif command == "full":
        cmd_full(task_id, args[2] if len(args) > 2 else "update")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
