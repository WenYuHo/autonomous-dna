# CLAUDE.md
# Claude Code platform file.
# Read AGENTS.md first — this file adds Claude Code specifics only.

---

## ENFORCEMENT LAYER — READ THIS FIRST
Hooks in `.claude/settings.json` enforce the hard rules mechanically.
**Hooks enforce. Prose documents. Never confuse the two.**

Active hooks:
- `PreToolUse` → blocks writes to all scaffold files. Returns a stop signal to Claude.
- `SessionStart` → re-injects HARD RULES into context at every session start.

If you encounter a hook rejection, do NOT attempt to work around it.
Log the situation in MEMORY.md and add a task for human review.

Security note: `.claude/settings.json` is committed to this repo.
Never blindly trust a forked version of this file — verify its contents before running.

---

## CONFIG FILES
```
AGENTS.md                    ← universal rules (read first, always)
CLAUDE.md                    ← this file: Claude Code specifics
.claude/settings.json        ← enforcement: hooks + permissions (committed)
.claude/settings.local.json  ← your personal overrides (GITIGNORED — never commit)
.mcp.json                    ← MCP servers with pinned versions (committed)
.claude/agents/              ← subagent definitions
.claude/commands/            ← custom slash commands
skills/                      ← load on demand, never upfront
```

---

## CONTEXT MANAGEMENT
- At ~60% context → run `/compact`
  Tell it: "compact — preserve current task ID, modified files, open decisions."
- Use `/clear` between unrelated tasks.
- After ~30–40 tool uses → start a new session. Run `python tools/session_start.py`
  to rehydrate from TASK_QUEUE.md + MEMORY.md.
- Delegate research and review to subagents — keeps your context focused.
- NEVER load all skills upfront. Load only the skill you need, when you need it.

---

## SUBAGENTS
Defined in `.claude/agents/`. Subagents return summaries only — never edit files.
- `researcher` — finds facts about a library/API
- `reviewer` — reviews a diff for correctness, tests, and security

---

## CUSTOM COMMANDS
- `/project:loop` — pick next task from TASK_QUEUE.md and run the core loop
- `/project:sync` — show queue status and memory summary
- `/project:health` — check context degradation indicators

---

## MODELS
- Architecture, complex multi-file work: `claude-opus-4-6`
- Standard day-to-day tasks: `claude-sonnet-4-6` (default)
- Quick single-file edits: `claude-haiku-4-5`

---

## MCP TOOLS
See `.mcp.json` for configured servers. All versions are pinned — never use `latest`.
Common patterns: `mcp__github__*` for PRs, `mcp__memory__*` for cross-session facts.

---

## SECURITY
- No secrets in CLAUDE.md — use environment variables only.
- Personal permission overrides → `settings.local.json` only (gitignored).
- Never set `"enableAllProjectMcpServers": true` — supply chain risk.
- Never trust a forked `.claude/settings.json` without reading it first.
