import os
import shlex
import subprocess
import sys


def run(args, check=False):
    return subprocess.run(args, capture_output=True, text=True, check=check)


def run_cmd(args):
    try:
        return run(args, check=True).stdout.strip()
    except Exception:
        return None


def _branch_exists(branch_name):
    refs = [f"refs/heads/{branch_name}", f"refs/remotes/origin/{branch_name}"]
    for ref in refs:
        if run(["git", "show-ref", "--verify", "--quiet", ref]).returncode == 0:
            return True
    return False


def resolve_base_branch():
    preferred = os.environ.get("AUTODNA_GIT_BASE_BRANCH", "").strip()
    candidates = [preferred, "dev", "main", "master"]
    for candidate in candidates:
        if candidate and _branch_exists(candidate):
            return candidate
    current = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    return current or "main"


def _parse_branch_status(output):
    state = {
        "branch": None,
        "upstream": None,
        "ahead": 0,
        "behind": 0,
        "dirty": False,
    }
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# branch.head "):
            state["branch"] = line.removeprefix("# branch.head ").strip()
            continue
        if line.startswith("# branch.upstream "):
            state["upstream"] = line.removeprefix("# branch.upstream ").strip()
            continue
        if line.startswith("# branch.ab "):
            parts = line.split()
            if len(parts) >= 4:
                try:
                    state["ahead"] = int(parts[2].lstrip("+"))
                    state["behind"] = int(parts[3].lstrip("-"))
                except ValueError:
                    pass
            continue
        if not line.startswith("#"):
            state["dirty"] = True
    return state


def inspect_git_state(fetch=True):
    state = {
        "ok": False,
        "issues": [],
        "branch": None,
        "upstream": None,
        "ahead": 0,
        "behind": 0,
        "dirty": False,
        "fetched": False,
    }

    if not os.path.exists(".git"):
        state["issues"].append("Current directory is not a git repository.")
        return state

    status = run(["git", "status", "--porcelain=v2", "--branch"], check=False)
    if status.returncode != 0:
        state["issues"].append("Unable to read git status.")
        return state

    state.update(_parse_branch_status(status.stdout))

    if fetch and state["upstream"]:
        remote = state["upstream"].split("/", 1)[0]
        fetch_result = run(["git", "fetch", remote, "--prune"], check=False)
        if fetch_result.returncode != 0:
            state["issues"].append(f"Unable to fetch latest refs from {remote}.")
            return state
        state["fetched"] = True
        refreshed = run(["git", "status", "--porcelain=v2", "--branch"], check=False)
        if refreshed.returncode != 0:
            state["issues"].append("Unable to refresh git status after fetch.")
            return state
        state.update(_parse_branch_status(refreshed.stdout))

    if not state["branch"] or state["branch"] in {"(detached)", "HEAD"}:
        state["issues"].append("Current checkout is detached; switch to a tracked branch before self-improve.")
    if not state["upstream"]:
        state["issues"].append("Current branch has no upstream tracking branch.")
    if state["dirty"]:
        state["issues"].append("Working tree has uncommitted or untracked changes.")
    if state["behind"] and state["ahead"]:
        state["issues"].append(
            f"Branch has diverged from upstream ({state['ahead']} ahead, {state['behind']} behind)."
        )
    elif state["behind"]:
        state["issues"].append(f"Branch is behind upstream by {state['behind']} commit(s).")
    elif state["ahead"]:
        state["issues"].append(
            f"Branch is ahead of upstream by {state['ahead']} commit(s); ship pending commits first."
        )

    state["ok"] = not state["issues"]
    return state


def run_tests():
    cmd = os.environ.get("AUTODNA_GIT_TEST_CMD", "pytest").strip()
    if not cmd:
        return
    result = run(shlex.split(cmd))
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def git_init(tid):
    if not os.path.exists(".git"):
        return False
    branch_name = f"agent/{tid.lower()}"
    base_branch = resolve_base_branch()
    run(["git", "checkout", base_branch], check=False)
    run(["git", "pull", "origin", base_branch, "--rebase"], check=False)
    run(["git", "checkout", "-B", branch_name], check=False)
    print(f"OK: {branch_name}")
    return True


def git_push(tid, msg):
    run_tests()
    full_message = f"[{tid}] {msg}"
    run(["git", "add", "."], check=False)
    run(["git", "commit", "-m", full_message], check=False)
    branch_name = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if branch_name:
        run(["git", "push", "origin", branch_name, "--force-with-lease"], check=False)
        print(f"OK: PUSH {branch_name}")


def git_pr(tid, body=""):
    if run_cmd(["gh", "--version"]) is None:
        return
    title = f"Autonomous Improvement: {tid}"
    base_branch = resolve_base_branch()
    url = run_cmd(["gh", "pr", "create", "--title", title, "--body", body, "--base", base_branch])
    if url:
        print(f"OK: PR {url}")


def monitor_ci(tid):
    import time

    for _ in range(30):
        status = run_cmd(["gh", "pr", "checks", "--json", "state,status", "--jq", ".[] | {state, status}"])
        if status and "PENDING" not in status and "IN_PROGRESS" not in status:
            if "FAILURE" in status or "ERROR" in status:
                return False
            return True
        time.sleep(30)
    return False


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(1)
    task_id = sys.argv[1]
    action = sys.argv[2]
    if action == "init":
        git_init(task_id)
    elif action == "commit":
        git_push(task_id, sys.argv[3] if len(sys.argv) > 3 else "Update")
    elif action == "pr":
        git_pr(task_id, sys.argv[3] if len(sys.argv) > 3 else "Autonomous contribution")
    elif action == "monitor":
        sys.exit(0 if monitor_ci(task_id) else 1)
