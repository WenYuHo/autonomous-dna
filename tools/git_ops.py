"""
tools/git_ops.py
Autonomous git flow: branch, commit, PR, rebase, merge.

Usage:
  python tools/git_ops.py TASK_ID full "commit message" [pr_body]
  python tools/git_ops.py TASK_ID init [branch_description]
  python tools/git_ops.py TASK_ID commit "msg"
  python tools/git_ops.py TASK_ID pr [optional_pr_body]
  python tools/git_ops.py TASK_ID merge [pr_url_or_number]
"""

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone


PROTECTED_BRANCHES = {"main", "master", "develop"}
SCAFFOLD_MARKERS = {
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".mcp.json",
    ".claude/settings.json",
}
LOCK_AND_GENERATED_BASENAMES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
    "pipfile.lock",
    "cargo.lock",
    "composer.lock",
    "gemfile.lock",
    "go.sum",
}
LOCK_AND_GENERATED_SUFFIXES = (
    ".lock",
    ".pb.go",
)
NON_FAILING_COMMIT_PHRASES = (
    "nothing to commit",
    "nothing added to commit",
    "no changes added to commit",
)


def run(cmd, check=False, cwd=None):
    return subprocess.run(cmd, capture_output=True, text=True, check=check, cwd=cwd)


def run_cmd(cmd):
    try:
        return run(cmd, check=True).stdout.strip()
    except Exception:
        return None


def _run_json(cmd):
    result = run(cmd, check=False)
    if result.returncode != 0:
        return None
    output = (result.stdout or "").strip()
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return None


def _parse_command(command):
    return shlex.split(command, posix=(os.name != "nt"))


def _branch_exists(branch_name):
    local = run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"], check=False)
    if local.returncode == 0:
        return True
    remote = run(["git", "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{branch_name}"], check=False)
    return remote.returncode == 0


def _slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "update"


def branch_name(task_id, description=""):
    prefix = os.environ.get("AUTODNA_GIT_BRANCH_PREFIX", "feat/").strip() or "feat/"
    if not prefix.endswith("/"):
        prefix = f"{prefix}/"
    base = f"{prefix}{task_id.lower()}"
    if description:
        return f"{base}-{_slugify(description)}"
    return base


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_base_branch():
    env_branch = os.environ.get("AUTODNA_GIT_BASE_BRANCH") or os.environ.get("AUTODNA_BASE_BRANCH")
    candidates = [env_branch, "dev", "main", "master"]
    for candidate in candidates:
        if candidate and _branch_exists(candidate):
            return candidate
    return "main"


def _current_branch():
    return run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])


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


def is_lab_mode():
    env_val = os.getenv("AUTODNA_LAB_MODE", "").strip().lower()
    if env_val in {"1", "track", "true", "yes"}:
        return True
    if env_val in {"0", "false", "no"}:
        return False
    cwd = os.getcwd().lower()
    if cwd.endswith("\\lab") or cwd.endswith("/lab") or "-lab" in cwd:
        return True
    branch = _current_branch()
    if branch and (branch.startswith("lab-") or branch.startswith("agent/")):
        return True
    return False


def inspect_git_state(fetch=True, allow_dirty=False):
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

    lab_mode = allow_dirty
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
    if not state["upstream"] and not lab_mode:
        state["issues"].append("Current branch has no upstream tracking branch.")
    if state["dirty"] and not lab_mode:
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
    test_cmd = os.environ.get("AUTODNA_GIT_TEST_CMD", "python -m pytest tests/")
    if not test_cmd.strip():
        return
    result = run(_parse_command(test_cmd), check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _is_protected_branch(branch):
    return branch in PROTECTED_BRANCHES


def _commit_output_has_non_fatal_message(result):
    text = f"{result.stdout}\n{result.stderr}".lower()
    return any(phrase in text for phrase in NON_FAILING_COMMIT_PHRASES)


def _is_scaffold_conflict(file_path):
    normalized = file_path.replace("\\", "/")
    for marker in SCAFFOLD_MARKERS:
        if normalized.endswith(marker):
            return True
    return False


def _resolution_for_conflict(path):
    basename = os.path.basename(path).lower()
    lower_path = path.lower()
    if basename in LOCK_AND_GENERATED_BASENAMES:
        return "base"
    if basename.endswith(LOCK_AND_GENERATED_SUFFIXES):
        return "base"
    if "/generated/" in lower_path or "\\generated\\" in lower_path:
        return "base"
    return "task"


def _checkout_side_for_rebase(resolution):
    # During rebase, `--ours` is upstream/base and `--theirs` is the rebased commit.
    if resolution == "base":
        return "ours"
    if resolution == "task":
        return "theirs"
    raise ValueError(f"Unknown conflict resolution policy: {resolution}")


def _log_conflict(task_id, file_path, resolution):
    memory_path = os.getenv("AUTODNA_MEMORY_FILE", "agent/MEMORY.md")
    detail = resolution
    try:
        checkout_side = _checkout_side_for_rebase(resolution)
        detail = f"{resolution} (rebase checkout --{checkout_side})"
    except ValueError:
        pass
    line = f"- [{now_iso()[:10]}] conflict on {file_path} during {task_id}, resolution: {detail}\n"
    try:
        with open(memory_path, "a", encoding="utf-8") as handle:
            handle.write(line)
    except Exception:
        pass


def _list_conflict_files():
    output = run_cmd(["git", "diff", "--name-only", "--diff-filter=U"])
    if not output:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def _rebase_with_retry(task_id, base_branch, max_attempts=3):
    for _ in range(max_attempts):
        result = run(["git", "rebase", f"origin/{base_branch}"], check=False)
        if result.returncode == 0:
            return True

        conflicts = _list_conflict_files()
        if not conflicts:
            run(["git", "rebase", "--abort"], check=False)
            return False

        for file_path in conflicts:
            if _is_scaffold_conflict(file_path):
                run(["git", "rebase", "--abort"], check=False)
                return False

            resolution = _resolution_for_conflict(file_path)
            checkout_side = _checkout_side_for_rebase(resolution)
            checkout = run(["git", "checkout", f"--{checkout_side}", "--", file_path], check=False)
            if checkout.returncode != 0:
                run(["git", "rebase", "--abort"], check=False)
                return False
            run(["git", "add", "--", file_path], check=False)
            _log_conflict(task_id, file_path, resolution)

        cont = run(["git", "rebase", "--continue"], check=False)
        if cont.returncode == 0:
            return True

    run(["git", "rebase", "--abort"], check=False)
    return False


def _count_commits(range_expr):
    value = run_cmd(["git", "rev-list", "--count", range_expr])
    if value is None:
        return 0
    try:
        return int(value.strip())
    except ValueError:
        return 0


def _gh_available():
    return run_cmd(["gh", "--version"]) is not None


def _origin_repo_slug():
    remote_url = run_cmd(["git", "remote", "get-url", "origin"])
    if not remote_url:
        return None
    remote_url = remote_url.strip()
    match = re.search(r"github\.com[:/](?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?$", remote_url)
    if not match:
        return None
    owner = match.group("owner")
    repo = match.group("repo")
    if not owner or not repo:
        return None
    return f"{owner}/{repo}"


def _gh_command(args, repo=None):
    slug = repo or _origin_repo_slug()
    if slug:
        return ["gh", "--repo", slug, *args]
    return ["gh", *args]


def _gh_run(args, repo=None, cwd=None, check=False):
    return run(_gh_command(args, repo=repo), check=check, cwd=cwd)


def _gh_run_cmd(args, repo=None, cwd=None):
    if repo is None and cwd is None:
        return run_cmd(["gh", *args])
    try:
        return _gh_run(args, repo=repo, cwd=cwd, check=True).stdout.strip()
    except Exception:
        return None


def _gh_run_json(args, repo=None, cwd=None):
    if repo is None and cwd is None:
        return _run_json(["gh", *args])
    result = _gh_run(args, repo=repo, cwd=cwd, check=False)
    if result.returncode != 0:
        return None
    output = (result.stdout or "").strip()
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return None


def _find_open_pr_for_head(head_branch, repo=None):
    prs = _gh_run_json(["pr", "list", "--head", head_branch, "--state", "open", "--json", "url,number"], repo=repo)
    if not prs:
        return None
    return prs[0].get("url") or str(prs[0].get("number"))


def _gh_pr_view_field(pr_ref, field, repo=None):
    return _gh_run_cmd(["pr", "view", str(pr_ref), "--json", field, "--jq", f".{field}"], repo=repo)


def _parse_worktree_list_porcelain(output):
    worktrees = []
    current = None
    for raw_line in (output or "").splitlines():
        line = raw_line.rstrip()
        if not line:
            if current:
                worktrees.append(current)
                current = None
            continue

        key, _, value = line.partition(" ")
        value = value.strip()
        if key == "worktree":
            if current:
                worktrees.append(current)
            current = {
                "path": value,
                "branch": None,
                "head": None,
                "bare": False,
                "detached": False,
                "locked": False,
                "prunable": False,
            }
            continue
        if current is None:
            continue
        if key == "branch":
            current["branch"] = value.removeprefix("refs/heads/")
        elif key == "HEAD":
            current["head"] = value
        elif key == "bare":
            current["bare"] = True
        elif key == "detached":
            current["detached"] = True
        elif key == "locked":
            current["locked"] = True
        elif key == "prunable":
            current["prunable"] = True
    if current:
        worktrees.append(current)
    return worktrees


def _list_worktrees():
    output = run_cmd(["git", "worktree", "list", "--porcelain"])
    if output is None:
        return []
    return _parse_worktree_list_porcelain(output)


def _repo_root_path():
    root = run_cmd(["git", "rev-parse", "--show-toplevel"])
    return root or os.getcwd()


def _norm_path(path):
    return os.path.normcase(os.path.abspath(path))


def _is_same_path(left, right):
    try:
        return _norm_path(left) == _norm_path(right)
    except Exception:
        return False


def _git_ref_exists(ref_name):
    return run(["git", "rev-parse", "--verify", "--quiet", ref_name], check=False).returncode == 0


def _is_branch_merged_into(branch, base_branch):
    if not branch or not base_branch:
        return False
    merge_targets = [f"origin/{base_branch}", base_branch]
    for target in merge_targets:
        if not _git_ref_exists(target):
            continue
        probe = run(["git", "merge-base", "--is-ancestor", branch, target], check=False)
        if probe.returncode == 0:
            return True
    return False


def _remote_branch_exists(branch):
    if not branch:
        return False
    probe = run(["git", "ls-remote", "--exit-code", "--heads", "origin", branch], check=False)
    return probe.returncode == 0


def _safe_remove_worktree(path, current_worktree_path):
    if not path or _is_same_path(path, current_worktree_path):
        return False
    removed = run(["git", "worktree", "remove", path], check=False)
    return removed.returncode == 0


def _safe_delete_local_branch(branch, current_branch, branch_in_worktrees, base_branch):
    if not branch or _is_protected_branch(branch):
        return False
    if current_branch and branch == current_branch:
        return False
    if branch_in_worktrees:
        return False
    if not _is_branch_merged_into(branch, base_branch):
        return False
    deleted = run(["git", "branch", "-d", branch], check=False)
    return deleted.returncode == 0


def _cleanup_merged_branch_artifacts(merged_branch, base_branch):
    if not merged_branch or _is_protected_branch(merged_branch):
        return {"worktrees_removed": [], "local_branch_deleted": False, "remote_branch_deleted": False}

    current_branch = _current_branch()
    current_worktree_path = _repo_root_path()
    removed_paths = []

    run(["git", "worktree", "prune"], check=False)
    worktrees = _list_worktrees()
    for worktree in worktrees:
        if worktree.get("branch") != merged_branch:
            continue
        path = worktree.get("path")
        if _safe_remove_worktree(path, current_worktree_path):
            removed_paths.append(path)

    run(["git", "worktree", "prune"], check=False)
    run(["git", "fetch", "origin", "--prune"], check=False)

    remaining = _list_worktrees()
    branches_in_worktrees = {wt.get("branch") for wt in remaining if wt.get("branch")}
    local_deleted = _safe_delete_local_branch(
        merged_branch,
        current_branch=current_branch,
        branch_in_worktrees=(merged_branch in branches_in_worktrees),
        base_branch=base_branch,
    )

    remote_deleted = False
    if _remote_branch_exists(merged_branch):
        remote_deleted = run(["git", "push", "origin", "--delete", merged_branch], check=False).returncode == 0

    return {
        "worktrees_removed": removed_paths,
        "local_branch_deleted": local_deleted,
        "remote_branch_deleted": remote_deleted,
    }


def _is_worktree_merge_conflict(message):
    text = (message or "").lower()
    checks = ("worktree", "already used by worktree", "already checked out")
    return any(check in text for check in checks)


def _parse_checks_state(checks):
    if checks is None:
        return "unknown"
    if not checks:
        return "success"
    states = {str(item.get("state", "")).upper() for item in checks}
    failing = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"}
    pending = {"PENDING", "IN_PROGRESS", "QUEUED", "WAITING"}
    if states & failing:
        return "failure"
    if states & pending:
        return "pending"
    return "success"


def _gh_pr_checks(pr_ref, repo=None):
    result = _gh_run(["pr", "checks", str(pr_ref), "--json", "state"], repo=repo, check=False)
    if result.returncode == 0:
        output = (result.stdout or "").strip()
        if not output:
            return []
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return None

    message = f"{result.stdout}\n{result.stderr}".lower()
    if "no checks reported" in message:
        return []
    return None


def monitor_ci(pr_ref, poll_seconds=None, max_polls=None, repo=None):
    poll_seconds = poll_seconds or int(os.getenv("AUTODNA_GIT_CI_POLL_SECONDS", "10"))
    max_polls = max_polls or int(os.getenv("AUTODNA_GIT_CI_MAX_POLLS", "30"))
    for _ in range(max_polls):
        checks = _gh_pr_checks(pr_ref, repo=repo)
        parsed = _parse_checks_state(checks)
        if parsed == "success":
            return True
        if parsed == "failure":
            return False
        if parsed == "unknown":
            return None
        time.sleep(poll_seconds)
    return None


def git_init(task_id, description=""):
    if not os.path.exists(".git"):
        return False
    run(["git", "fetch", "origin"], check=False)
    base_branch = resolve_base_branch()
    run(["git", "checkout", base_branch], check=False)
    run(["git", "pull", "origin", base_branch], check=False)
    branch = branch_name(task_id, description)
    created = run(["git", "checkout", "-b", branch], check=False)
    if created.returncode != 0:
        switched = run(["git", "checkout", branch], check=False)
        if switched.returncode != 0:
            return False
    print(f"On branch: {branch}")
    return True


def git_push(task_id, msg):
    run(["git", "add", "-A"], check=False)
    staged_check = run(["git", "diff", "--cached", "--quiet"], check=False)
    if staged_check.returncode == 0:
        print("Nothing to commit.")
        return True

    run_tests()
    commit_message = f"{msg}\n\nTASK_ID: {task_id}"
    commit = run(["git", "commit", "-m", commit_message], check=False)
    if commit.returncode != 0 and not _commit_output_has_non_fatal_message(commit):
        return False

    base_branch = resolve_base_branch()
    run(["git", "fetch", "origin"], check=False)
    if not _rebase_with_retry(task_id, base_branch):
        return False

    branch = _current_branch() or branch_name(task_id)
    if _is_protected_branch(branch):
        return False

    pushed = run(["git", "push", "--force-with-lease", "origin", branch], check=False)
    if pushed.returncode != 0:
        return False
    print(f"Committed, rebased, and pushed: {branch}")
    return True


def git_pr(task_id, body=""):
    if not _gh_available():
        return None

    repo_slug = _origin_repo_slug()
    branch = _current_branch() or branch_name(task_id)
    base_branch = resolve_base_branch()

    run(["git", "fetch", "origin"], check=False)
    behind = _count_commits(f"{branch}..origin/{base_branch}")
    if behind > 0:
        if not _rebase_with_retry(task_id, base_branch):
            return None
        if _is_protected_branch(branch):
            return None
        pushed = run(["git", "push", "--force-with-lease", "origin", branch], check=False)
        if pushed.returncode != 0:
            return None

    if repo_slug:
        existing = _find_open_pr_for_head(branch, repo=repo_slug)
    else:
        existing = _find_open_pr_for_head(branch)
    if existing:
        print(f"OK: PR {existing}")
        return existing

    draft = os.getenv("AUTODNA_GIT_DRAFT_PR", "1").strip().lower() in {"1", "true", "yes"}
    cmd = ["pr", "create", "--base", base_branch, "--head", branch]
    if draft:
        cmd.append("--draft")
    if body:
        cmd.extend(["--title", f"Autonomous Improvement: {task_id}", "--body", body])
    else:
        cmd.append("--fill")

    url = _gh_run_cmd(cmd, repo=repo_slug)
    if url:
        print(f"PR opened: {url}")
    return url


def git_merge(task_id, pr_ref=None):
    if not _gh_available():
        return False

    repo_slug = _origin_repo_slug()
    branch = _current_branch() or branch_name(task_id)
    if not pr_ref:
        if repo_slug:
            pr_ref = _find_open_pr_for_head(branch, repo=repo_slug)
        else:
            pr_ref = _find_open_pr_for_head(branch)
    if not pr_ref:
        return False

    head_branch = _gh_pr_view_field(pr_ref, "headRefName", repo=repo_slug) or branch
    max_rebases = int(os.getenv("AUTODNA_GIT_REBASE_MAX_ATTEMPTS", "3"))
    base_branch = _gh_pr_view_field(pr_ref, "baseRefName", repo=repo_slug) or resolve_base_branch()

    for _ in range(max_rebases + 1):
        merge_state = (_gh_pr_view_field(pr_ref, "mergeStateStatus", repo=repo_slug) or "").upper()
        if merge_state in {"BEHIND", "DIRTY"}:
            if not _rebase_with_retry(task_id, base_branch, max_attempts=max_rebases):
                return False
            if _is_protected_branch(branch):
                return False
            pushed = run(["git", "push", "--force-with-lease", "origin", branch], check=False)
            if pushed.returncode != 0:
                return False
            continue

        if merge_state == "DRAFT":
            _gh_run(["pr", "ready", str(pr_ref)], repo=repo_slug, check=False)

        ci_status = monitor_ci(pr_ref, repo=repo_slug)
        if ci_status is not True:
            return False

        with tempfile.TemporaryDirectory() as neutral_cwd:
            merged = _gh_run(
                ["pr", "merge", str(pr_ref), "--squash", "--delete-branch"],
                repo=repo_slug,
                cwd=neutral_cwd,
                check=False,
            )
        if merged.returncode == 0:
            _cleanup_merged_branch_artifacts(head_branch, base_branch)
            print(f"Merged and branch deleted: {pr_ref}")
            return True

        merge_text = f"{merged.stdout}\n{merged.stderr}".lower()
        if _is_worktree_merge_conflict(merge_text):
            with tempfile.TemporaryDirectory() as neutral_cwd:
                retry_merge = _gh_run(
                    ["pr", "merge", str(pr_ref), "--squash"],
                    repo=repo_slug,
                    cwd=neutral_cwd,
                    check=False,
                )
            if retry_merge.returncode == 0:
                _cleanup_merged_branch_artifacts(head_branch, base_branch)
                print(f"Merged and branch deleted: {pr_ref}")
                return True
            merge_text = f"{retry_merge.stdout}\n{retry_merge.stderr}".lower()

        if "behind" in merge_text or "update branch" in merge_text:
            if not _rebase_with_retry(task_id, base_branch, max_attempts=max_rebases):
                return False
            if _is_protected_branch(branch):
                return False
            pushed = run(["git", "push", "--force-with-lease", "origin", branch], check=False)
            if pushed.returncode != 0:
                return False
            continue
        return False

    return False


def git_full(task_id, msg, body=""):
    if not git_init(task_id, msg):
        return False
    if not git_push(task_id, msg):
        return False
    pr_ref = git_pr(task_id, body=body)
    if not pr_ref:
        return False
    return git_merge(task_id, pr_ref=pr_ref)


def main(argv=None):
    args = list(argv if argv is not None else sys.argv[1:])
    if len(args) < 2:
        print(__doc__)
        return 0

    task_id = args[0]
    command = args[1]

    if command == "init":
        return 0 if git_init(task_id, args[2] if len(args) > 2 else "") else 1
    if command == "commit":
        return 0 if git_push(task_id, args[2] if len(args) > 2 else "update") else 1
    if command == "pr":
        return 0 if git_pr(task_id, args[2] if len(args) > 2 else "") else 1
    if command == "merge":
        return 0 if git_merge(task_id, args[2] if len(args) > 2 else None) else 1
    if command == "monitor":
        return 0 if monitor_ci(args[2] if len(args) > 2 else "") else 1
    if command == "full":
        msg = args[2] if len(args) > 2 else "update"
        body = args[3] if len(args) > 3 else ""
        return 0 if git_full(task_id, msg, body=body) else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
