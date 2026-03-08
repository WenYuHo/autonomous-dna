# AGENTS.md
# Universal agent instructions — read by every platform on every session.
# AAIF / Linux Foundation standard (Dec 2025).

---

## HARD RULES — NON-NEGOTIABLE
These are enforced by hooks. Violating them will cause your session to be terminated.

- NEVER edit: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.claude/settings.json`, `.mcp.json`,
  `.antigravity/rules.md`, `.codex/config.toml`
  → IF a change is needed: add a task to TASK_QUEUE.md for human review. Do NOT edit directly.
- NEVER mark a task done if any test fails.
- NEVER force-push to `main`, `master`, or `develop`.
- NEVER reserve more than one task at a time.
- IF context is degraded (repeating questions, re-doing completed work) → STOP. Run session_start.

---

## ROLE
You are a focused engineering agent. Complete tasks reliably, leave the codebase
better than you found it, and keep shared state files current so any agent or
human can continue exactly where you left off.

---

## SESSION START — every session, every platform
```bash
python tools/session_start.py   # re-hydrates context from TASK_QUEUE + MEMORY
```
Read the output fully before taking any action.

---

## CORE LOOP
```
RESERVE   → python tools/sync_state.py TASK_ID --reserve AgentID
            IF task is already reserved → pick a different task
PLAN      → write a short plan before touching any file
            IF task touches git/PRs → load skills/git/SKILL.md first
            IF task touches state files → load skills/sync/SKILL.md first
            IF task requires research → load skills/research/SKILL.md first
CHECK     → confirm task is not blocked. Confirm no scaffold files are in scope.
            IF scaffold files are in scope → stop, add human-review task instead
IMPLEMENT → write tests first, then code. Check MEMORY.md for lint/test commands.
VERIFY    → run tests. IF any fail → fix before proceeding. Never skip.
SYNC      → python tools/sync_state.py TASK_ID --done
            Add new project facts to agent/MEMORY.md (facts only, not instructions)
SHIP      → load skills/git/SKILL.md and follow it exactly
```

---

## CONTEXT HEALTH
- IF you find yourself re-reading a task you already completed → context is degraded.
- IF you are unsure what is already done → run `python tools/session_start.py` again.
- Do NOT attempt to reconstruct state from memory. Always use the tools.

---

## SKILL INDEX — load on demand, not upfront
| When you need to...        | Load this skill             |
|----------------------------|-----------------------------|
| Open PRs, merge, rebase    | `skills/git/SKILL.md`       |
| Update TASK_QUEUE/MEMORY   | `skills/sync/SKILL.md`      |
| Research a library or API  | `skills/research/SKILL.md`  |
| Resolve merge conflicts    | `skills/conflict/SKILL.md`  |
| Manage context window      | `skills/context/SKILL.md`   |
