"""
tools/guard_scaffold.py
Scaffold file protection for platforms without native hook support (Gemini, Codex, etc.).
Run at session start and before any file write operation.

Usage:
  python tools/guard_scaffold.py --check          # validate no scaffold violations exist
  python tools/guard_scaffold.py --file path/to/file  # check a specific file before writing
"""

import sys
from pathlib import Path

SCAFFOLD_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".mcp.json",
    ".claude/settings.json",
    ".codex/config.toml",
    ".antigravity/rules.md",
}


def check_file(path: str) -> None:
    normalised = path.lstrip("./")
    for scaffold in SCAFFOLD_FILES:
        if normalised == scaffold or path.endswith(scaffold):
            print(f"BLOCKED: '{path}' is a scaffold file.")
            print("Add a task to agent/TASK_QUEUE.md for human review instead.")
            sys.exit(1)
    print(f"OK: '{path}' is not a scaffold file.")


def check_all() -> None:
    root = Path.cwd()
    violations = []

    # Check git staging area for scaffold files
    import subprocess
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True,
    )
    staged = result.stdout.splitlines()

    for f in staged:
        normalised = f.lstrip("./")
        for scaffold in SCAFFOLD_FILES:
            if normalised == scaffold or f.endswith(scaffold):
                violations.append(f)

    if violations:
        print("GUARD VIOLATION: Scaffold files staged for commit:")
        for v in violations:
            print(f"  {v}")
        print("\nRun: git restore --staged <file>")
        print("Then add a task to agent/TASK_QUEUE.md for human review.")
        sys.exit(1)

    print("Guard check passed. No scaffold violations detected.")


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] == "--check":
        check_all()
    elif args[0] == "--file" and len(args) > 1:
        check_file(args[1])
    else:
        print(__doc__)
        sys.exit(0)


if __name__ == "__main__":
    main()
