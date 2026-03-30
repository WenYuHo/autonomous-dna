"""
autodna/tools/context.py
Implements the Context Manager Pattern.
Gathers and dumps project-wide context for agent awareness.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def get_git_status() -> str:
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False
        )
        return result.stdout.strip()
    except Exception:
        return "git not available or not a repo"

def get_git_log(n: int = 3) -> str:
    try:
        result = subprocess.run(
            ["git", "log", f"-n {n}", "--oneline"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False
        )
        return result.stdout.strip()
    except Exception:
        return ""

def get_file_tree(root: Path, max_depth: int = 2) -> dict:
    tree = {"files": [], "dirs": []}
    try:
        for item in root.iterdir():
            if item.name.startswith(".") or item.name == "__pycache__":
                continue
            if item.is_file():
                tree["files"].append(item.name)
            elif item.is_dir():
                tree["dirs"].append(item.name)
                # Recurse if needed, simplified for now
    except Exception as e:
        tree["error"] = str(e)
    return tree

def dump_context():
    context = {
        "cwd": os.getcwd(),
        "git_status": get_git_status(),
        "recent_commits": get_git_log(),
        "file_tree": get_file_tree(Path.cwd()),
        "env_vars": {
            "AUTODNA_PLATFORM": os.getenv("AUTODNA_PLATFORM"),
            "AUTODNA_MODELS": os.getenv("AUTODNA_MODELS"),
            "PATH": os.getenv("PATH", "")[:100] + "..." # Truncate for brevity
        }
    }
    print(json.dumps(context, indent=2))

def main():
    parser = argparse.ArgumentParser(description="Autonomous DNA Context Manager")
    parser.add_argument("action", choices=["dump"], help="Action to perform")
    args = parser.parse_args()

    if args.action == "dump":
        dump_context()

if __name__ == "__main__":
    main()
