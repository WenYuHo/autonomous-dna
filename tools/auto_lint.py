"""
tools/auto_lint.py
Reads lint command from agent/MEMORY.md and runs it.
Falls back to common linters if no entry found.

Usage:
  python tools/auto_lint.py
  python tools/auto_lint.py --fix
"""

import re
import subprocess
import sys
from pathlib import Path


def get_lint_command() -> list[str] | None:
    mem = Path("agent/MEMORY.md")
    if not mem.exists():
        return None
    for line in mem.read_text().splitlines():
        match = re.search(r"lint command:\s*(.+)", line)
        if match:
            return match.group(1).strip().split()
    return None


import shutil

def fallback_linters() -> list[list[str]]:
    candidates = [
        ["ruff", "check", "."],
        ["flake8", "."],
        ["eslint", "."],
        ["golangci-lint", "run"],
    ]
    available = []
    for cmd in candidates:
        if shutil.which(cmd[0]):
            available.append(cmd)
    return available


def main() -> None:
    fix_mode = "--fix" in sys.argv

    cmd = get_lint_command()
    if cmd:
        if fix_mode and "ruff" in cmd:
            cmd = ["ruff", "check", "--fix", "."]
        print(f"Running lint: {' '.join(cmd)}")
        result = subprocess.run(cmd)
        sys.exit(result.returncode)

    print("No lint command in MEMORY.md. Trying fallbacks...")
    linters = fallback_linters()
    if not linters:
        print("WARN: No linter found. Add lint command to agent/MEMORY.md:")
        print("  - [YYYY-MM-DD] lint command: ruff check .")
        sys.exit(0)

    for linter in linters:
        print(f"Running: {' '.join(linter)}")
        result = subprocess.run(linter)
        if result.returncode != 0:
            print(f"Lint failed. Add to MEMORY.md: lint command: {' '.join(linter)}")
            sys.exit(result.returncode)

    print("Lint passed.")


if __name__ == "__main__":
    main()
