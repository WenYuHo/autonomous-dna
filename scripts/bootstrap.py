import shutil
import sys
from pathlib import Path

def generate_file(path: Path, content: str) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.strip() + "\n", encoding="utf-8")
        print(f"Created: {path.relative_to(Path.cwd())}")

def copy_scaffold_item(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
        print(f"Copied directory: {src.name}/")
    else:
        shutil.copy2(src, dst)
        print(f"Copied file: {src.name}")

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    target_dir = Path.cwd()
    script_path = Path(__file__).resolve()
    # If run from /tmp/dna-install/scripts/bootstrap.py, source_dir is /tmp/dna-install
    source_dir = script_path.parent.parent

    print(f"Bootstrapping Autonomous-DNA into {target_dir}...")

    # 1. Copy core files and directories if source != target
    if source_dir != target_dir:
        items_to_copy = [
            "AGENTS.md", "CLAUDE.md", "_gitignore", "_mcp.json", "bridge.py",
            "tools", "skills"
        ]
        for item in items_to_copy:
            copy_scaffold_item(source_dir / item, target_dir / item)

    # 2. Auto-generate platform config files and hooks (idempotent)

    # GEMINI.md
    generate_file(target_dir / "GEMINI.md", """
# Gemini / Antigravity Platform Instructions
Read `AGENTS.md` before taking any action.

## TOOL ROUTING
- Antigravity IDE: load .antigravity/rules.md, then AGENTS.md in workspace root.
- Gemini CLI: focus on using tools locally and rely on `tools/session_start.py` to hydrate context.
""")

    # .codex/config.toml
    generate_file(target_dir / ".codex" / "config.toml", """
[agent]
welcome_message = "Autonomous DNA Codex agent initialized. Read AGENTS.md."
disable_telemetry = true
""")

    # .antigravity/rules.md
    generate_file(target_dir / ".antigravity" / "rules.md", """
# Antigravity Rules
Read `AGENTS.md` in the project root immediately after this file.
""")

    # .claude/settings.json
    generate_file(target_dir / ".claude" / "settings.json", """
{
  "customHooks": {
    "PreToolUse": "python .claude/hooks/guard_scaffold.py"
  }
}
""")

    # .claude/hooks/guard_scaffold.py
    generate_file(target_dir / ".claude" / "hooks" / "guard_scaffold.py", """
import sys
import os

def main():
    print("Executing guard_scaffold pre-tool hook...")
    sys.exit(0)

if __name__ == "__main__":
    main()
""")

    # .claude/hooks/inject_rules.py
    generate_file(target_dir / ".claude" / "hooks" / "inject_rules.py", """
import sys

def main():
    print("Executing inject_rules hook...")
    sys.exit(0)

if __name__ == "__main__":
    main()
""")

    # Ensure .claude/agents/ directory exists
    (target_dir / ".claude" / "agents").mkdir(parents=True, exist_ok=True)

    print("Bootstrap complete. Run `python bridge.py` next.")

if __name__ == "__main__":
    main()
