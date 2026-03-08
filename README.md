# Autonomous DNA

> **AI agent reading this?** → Follow [AGENT INSTRUCTIONS](#agent-instructions) below immediately.
> **Human developer?** → See [Human Setup](#human-setup).

---

## AGENT INSTRUCTIONS

You have been given this repo URL. Your job is to install this scaffold
into the current working project. Follow these steps exactly.

### Step 1 — Identify your platform
- Claude Code → read `CLAUDE.md` then `AGENTS.md` after setup
- Gemini CLI or Antigravity → read `GEMINI.md` then `AGENTS.md` after setup
- Codex CLI, Codex App, Cursor, Copilot, Windsurf, or anything else → read `AGENTS.md`

### Step 2 — Clone and run the installer
```bash
git clone --depth=1 https://github.com/YOUR_REPO_URL /tmp/dna-install
python /tmp/dna-install/scripts/bootstrap.py
rm -rf /tmp/dna-install
python bridge.py      # renames _gitignore → .gitignore and _mcp.json → .mcp.json
python tools/session_start.py
```

> Note: `_gitignore` and `_mcp.json` are stored with underscore prefix so they survive
> GitHub web upload. `bridge.py` renames them automatically on install.

### Step 3 — Verify setup
Confirm all of these exist before continuing:
- [ ] `AGENTS.md` at project root
- [ ] `agent/TASK_QUEUE.md`
- [ ] `agent/MEMORY.md`
- [ ] `platform/ACTIVE` (contains your detected platform name)
- [ ] `.claude/settings.json`
- [ ] `.claude/hooks/guard_scaffold.py`
- [ ] `.claude/hooks/inject_rules.py`
- [ ] `skills/` directory with git, sync, research, context, conflict skill files
- [ ] `tools/` directory with all scripts

### Step 4 — Read your platform file, then AGENTS.md
Load the right file for your platform (Step 1), then read `AGENTS.md`.

### Step 5 — Report to the developer
Tell the developer:
- Setup complete
- Platform detected: [name]
- First task in TASK_QUEUE.md: [task]
- Ask: "What would you like me to work on first?"

---

## Human Setup

### Give this repo to any agent in any project
```
"Bootstrap this project using [your repo URL]"
```
The agent reads this README, runs the installer, and is ready to work.

### Platforms supported
| Platform | Reads | Loop command |
|---|---|---|
| Claude Code | `CLAUDE.md` → `AGENTS.md` | `/project:loop` |
| Gemini CLI | `GEMINI.md` → `AGENTS.md` | `/ralph:loop` |
| Antigravity | `.antigravity/rules.md` → `AGENTS.md` | "start the loop" |
| Codex CLI / App | `AGENTS.md` | "start the loop" |
| Cursor / Copilot / Windsurf / Aider | `AGENTS.md` | "start the loop" |

### ⚠️ One-time fix on your machine (Antigravity + Gemini CLI conflict)
Both tools share `~/.gemini/GEMINI.md`. Add this to the top of that file once:
```markdown
## TOOL ROUTING
- Antigravity IDE: load .antigravity/rules.md, then AGENTS.md in workspace root.
- Gemini CLI: follow project GEMINI.md.
```

### Daily workflow
1. Open your agent
2. It reads the scaffold automatically on startup
3. Add tasks to `agent/TASK_QUEUE.md`
4. Agent runs `/project:loop` or `/ralph:loop` or you say "start the loop"
5. Agent codes, opens PRs, resolves conflicts, auto-merges when CI passes
6. You only get notified if CI fails or conflicts are unresolvable

---

## Design Philosophy

This scaffold is built for **AI agents as the primary reader**, not humans.
Every design decision follows from that constraint.

### Hooks enforce. Prose documents.
Prose instructions decay with context. `.claude/settings.json` hooks do not.
The scaffold separates what must always be true (hooks) from what guides good behavior (docs).

### Load skills on demand, not upfront
Context is a finite resource. `AGENTS.md` is intentionally lean — under 80 lines.
Skill files (`skills/*/SKILL.md`) are loaded only when the agent needs them.
This keeps the context window available for actual implementation work.

### Scripts handle deterministic logic
Everything predictable — reserving tasks, marking done, rebasing, merging — lives in
`tools/` as Python scripts. Agents call scripts; they do not re-derive logic from prose.

### State re-hydration over memory
Agents do not rely on remembering across context degradation.
`tools/session_start.py` always reconstructs current state from files.
This is why MEMORY.md contains facts, not instructions.

### Security
`.claude/settings.json` is committed to this repo and enforced via hooks.
Before running any forked version of this repo, verify this file's contents manually.
Malicious hooks could execute arbitrary commands — treat this file as code, not config.

---

## What every agent will do in your project
- Reserve tasks before starting (no two agents clash)
- Re-read project context from MEMORY.md every session via `session_start.py`
- Load skills on demand — never all at once
- Write tests before code
- Rebase, resolve conflicts, and auto-merge PRs autonomously
- Never edit scaffold files without your review
- Leave clean state for the next agent or session
