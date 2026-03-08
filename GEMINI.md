# GEMINI.md
# Used by: Gemini CLI (terminal) and Antigravity IDE (desktop).
# Read AGENTS.md first — this file adds platform specifics only.

---

## ENFORCEMENT LAYER — READ THIS FIRST
Gemini CLI has no native hook system. Enforcement is handled via session-start
validation and the guard script. Run this before every task:

```bash
python tools/session_start.py
python tools/guard_scaffold.py --check
```

If `guard_scaffold.py` reports violations, STOP. Do not proceed until resolved.
The guard script is your equivalent of Claude Code's PreToolUse hook.

---

## ⚠️ ANTIGRAVITY + GEMINI CLI CONFLICT — ONE-TIME FIX PER MACHINE
Both tools share `~/.gemini/GEMINI.md`. Add this to the TOP of that file once:

```
## TOOL ROUTING
- Antigravity IDE: load .antigravity/rules.md, then read AGENTS.md in workspace root.
- Gemini CLI terminal: follow project GEMINI.md.
- ~/.gemini/antigravity/ is Antigravity-only. Ignore it in CLI mode.
```

---

## FOR ANTIGRAVITY IDE
Before every task:
1. Read `AGENTS.md` fully.
2. Run `python tools/session_start.py` — read its full output.
3. Load only the skill you need for this task (see SKILL INDEX in AGENTS.md).
4. Follow the CORE LOOP from AGENTS.md exactly.

Settings:
- One agent per task (not one agent for everything)
- Generate an Artifact (plan) before writing code — let developer review first
- Spawn a subagent for research — never research + implement in same context window
- Sandbox: keep set to `strict`. Log permission issues in MEMORY.md and ask human.

---

## FOR GEMINI CLI
- Start the loop: `/ralph:loop` if available, otherwise follow AGENTS.md manually.
- Context limit: Gemini CLI does not auto-compact. Monitor manually.
  When near limit: start a new session, run `python tools/session_start.py` to rehydrate.
- NEVER load all skills upfront. Load only the skill file you need, when you need it.
- Research: if MEMORY.md has no entry for a library, load `skills/research/SKILL.md` first.

---

## MODELS
- Architecture, hard reasoning: Gemini 2.5 Pro, thinking enabled
- Standard implementation: Gemini 2.0 Pro
- Fast edits: Gemini 2.0 Flash
