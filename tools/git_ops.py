import os, subprocess, sys
from datetime import datetime

def run_cmd(args):
    try:
        r = subprocess.run(args, capture_output=True, text=True, check=True)
        return r.stdout.strip()
    except: return None

def git_init(tid):
    if not os.path.exists(".git"): return False
    bn = f"agent/{tid.lower()}"
    mb = run_cmd(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"])
    if mb: mb = mb.split("/")[-1]
    else: mb = "main"
    run_cmd(["git", "checkout", mb])
    run_cmd(["git", "pull", "origin", mb, "--rebase"])
    run_cmd(["git", "checkout", "-B", bn])
    print(f"OK: {bn}")

def git_push(tid, msg):
    fm = f"[{tid}] {msg}"
    run_cmd(["git", "add", "."])
    run_cmd(["git", "commit", "-m", fm])
    bn = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    run_cmd(["git", "push", "origin", bn, "--force-with-lease"])
    print(f"OK: PUSH {bn}")

def git_pr(tid, body=""):
    if run_cmd(["gh", "--version"]) is None: return
    t = f"Autonomous Improvement: {tid}"
    url = run_cmd(["gh", "pr", "create", "--title", t, "--body", body, "--base", "main"])
    if url: print(f"OK: PR {url}")

def monitor_ci(tid):
    import time
    for i in range(30):
        s = run_cmd(["gh", "pr", "checks", "--json", "state,status", "--jq", ".[] | {state, status}"])
        if s and "PENDING" not in s and "IN_PROGRESS" not in s:
            if "FAILURE" in s or "ERROR" in s: return False
            return True
        time.sleep(30)
    return False

if __name__ == "__main__":
    if len(sys.argv) < 3: sys.exit(1)
    tid = sys.argv[1]; act = sys.argv[2]
    if act == "init": git_init(tid)
    elif act == "commit": git_push(tid, sys.argv[3] if len(sys.argv) > 3 else "Update")
    elif act == "pr": git_pr(tid, sys.argv[3] if len(sys.argv) > 3 else "Autonomous contribution")
    elif act == "monitor": sys.exit(0 if monitor_ci(tid) else 1)
