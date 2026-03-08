"""
bridge.py — Detect platform, create state files, validate scaffold.
Run from project root: python bridge.py

Does NOT issue commands to the agent.
Enforcement lives in .claude/hooks/ (Claude Code) and tools/guard_scaffold.py (all others).

Platform detection order matters:
  ANTIGRAVITY is checked before GEMINI_CLI because Antigravity creates a .gemini/ folder,
  which would cause a false positive for GEMINI_CLI detection.
"""

import os
from datetime import datetime, timezone
from pathlib import Path


def log(msg: str) -> None:
    print(f"[bridge] {msg}")


def detect_platform() -> str:
    cwd = Path.cwd()

    if os.environ.get("GITHUB_ACTIONS") == "true":
        return "GITHUB_ACTIONS"

    checks = [
        # ANTIGRAVITY before GEMINI_CLI — Antigravity creates .gemini/ which would
        # trigger a false GEMINI_CLI detection if checked second.
        ("ANTIGRAVITY", [cwd / ".antigravity", cwd / ".gemini" / "antigravity"]),
        ("CLAUDE_CODE",  [cwd / "CLAUDE.md",    cwd / ".claudecode"]),
        ("GEMINI_CLI",   [cwd / "GEMINI.md",    cwd / ".gemini"]),
        ("CODEX",        [cwd / ".codex",        cwd / ".codex" / "config.toml"]),
        ("CURSOR",       [cwd / ".cursorrules",  cwd / ".cursor"]),
        ("WINDSURF",     [cwd / ".windsurfrules"]),
    ]

    for platform, paths in checks:
        if any(p.exists() for p in paths):
            return platform

    return "GENERIC"


def ensure_state_files(root: Path) -> list:
    (root / "agent").mkdir(exist_ok=True)
    created = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    tq = root / "agent" / "TASK_QUEUE.md"
    if not tq.exists():
        tq.write_text(
            f"# TASK QUEUE\n"
            f"# LAST_SYNC: {now}\n\n"
            f"## IN PROGRESS\n\n"
            f"## BACKLOG\n\n"
            f"- [ ] INITIAL_SETUP: Verify scaffold and define first real task.\n"
            f"    - Detail: Confirm AGENTS.md, tools/, skills/, and platform config are present.\n"
            f"    - Priority: HIGH\n"
            f"    - BlockedBy: NONE\n"
            f"    - Promise: SETUP_COMPLETE\n"
            f"    - Reserved: NONE\n"
            f"    - Done: NONE\n"
        )
        created.append("agent/TASK_QUEUE.md")

    mem = root / "agent" / "MEMORY.md"
    if not mem.exists():
        mem.write_text(
            f"# PROJECT MEMORY\n"
            f"# Hard limit: 150 lines. Facts only — no instructions.\n"
            f"# Format: - [YYYY-MM-DD] fact\n\n"
            f"## ENVIRONMENT\n"
            f"- [{now[:10]}] Bootstrapped with Autonomous DNA scaffold.\n\n"
            f"## PROJECT FACTS\n"
            f"# Add facts as you learn them:\n"
            f"# - [YYYY-MM-DD] lint command: ruff check .\n"
            f"# - [YYYY-MM-DD] test command: pytest -x\n"
        )
        created.append("agent/MEMORY.md")

    return created


def rename_dotfiles(root: Path) -> list:
    """Rename _gitignore/_mcp.json → .gitignore/.mcp.json on install.
    Files are stored with underscore prefix so they survive GitHub web upload.
    """
    renames = [
        ("_gitignore", ".gitignore"),
        ("_mcp.json",  ".mcp.json"),
    ]
    done = []
    for src, dst in renames:
        src_path = root / src
        dst_path = root / dst
        if src_path.exists() and not dst_path.exists():
            src_path.rename(dst_path)
            done.append(f"{src} → {dst}")
    return done


def write_active_platform(root: Path, platform: str) -> None:
    (root / "platform").mkdir(exist_ok=True)
    (root / "platform" / "ACTIVE").write_text(platform + "\n")


def validate(root: Path) -> list:
    warnings = []
    checks = [
        # Core instruction files
        (root / "AGENTS.md",                    "AGENTS.md missing — universal agent instructions"),
        (root / "CLAUDE.md",                    "CLAUDE.md missing — Claude Code platform file"),
        (root / "GEMINI.md",                    "GEMINI.md missing — Gemini/Antigravity platform file"),
        # Enforcement
        (root / ".claude" / "settings.json",    ".claude/settings.json missing — no hook enforcement"),
        (root / ".claude" / "hooks" / "guard_scaffold.py", ".claude/hooks/guard_scaffold.py missing — scaffold unprotected"),
        (root / ".claude" / "hooks" / "inject_rules.py",   ".claude/hooks/inject_rules.py missing — no rule injection"),
        # MCP
        (root / ".mcp.json" if (root / ".mcp.json").exists() else root / "_mcp.json",
                                                ".mcp.json / _mcp.json missing — no MCP servers configured"),
        # Platform support
        (root / ".codex" / "config.toml",       ".codex/config.toml missing — Codex unsupported"),
        (root / ".antigravity" / "rules.md",    ".antigravity/rules.md missing — Antigravity unsupported"),
        # Tools
        (root / "tools" / "session_start.py",   "tools/session_start.py missing"),
        (root / "tools" / "sync_state.py",      "tools/sync_state.py missing"),
        (root / "tools" / "git_ops.py",         "tools/git_ops.py missing"),
        (root / "tools" / "guard_scaffold.py",  "tools/guard_scaffold.py missing"),
        (root / "tools" / "auto_lint.py",       "tools/auto_lint.py missing"),
        # Skills
        (root / "skills" / "git" / "SKILL.md",      "skills/git/SKILL.md missing"),
        (root / "skills" / "sync" / "SKILL.md",     "skills/sync/SKILL.md missing"),
        (root / "skills" / "research" / "SKILL.md", "skills/research/SKILL.md missing"),
        (root / "skills" / "context" / "SKILL.md",  "skills/context/SKILL.md missing"),
        (root / "skills" / "conflict" / "SKILL.md", "skills/conflict/SKILL.md missing"),
        # Agents
        (root / ".claude" / "agents",           ".claude/agents/ missing — no subagent definitions"),
    ]
    for path, msg in checks:
        if not path.exists():
            warnings.append(msg)
    return warnings


def main() -> None:
    root = Path.cwd()
    platform = detect_platform()
    log(f"Platform: {platform}")

    for r in rename_dotfiles(root):
        log(f"Renamed: {r}")

    write_active_platform(root, platform)

    for f in ensure_state_files(root):
        log(f"Created: {f}")

    warnings = validate(root)
    for w in warnings:
        log(f"WARN: {w}")

    if not warnings:
        log("All checks passed.")
        log("Next: read AGENTS.md, then run python tools/session_start.py")
    else:
        log(f"{len(warnings)} issue(s) found. Some may be optional for your platform.")
        log("Run scripts/bootstrap.py to fix missing files.")

    log("Done.")


if __name__ == "__main__":
    main()
