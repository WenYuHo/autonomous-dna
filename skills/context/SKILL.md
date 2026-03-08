# SKILL: Context Management
# Load this file ONLY when you notice context degradation symptoms.
# Do NOT load at session start — load on demand only.

---

## DEGRADATION SYMPTOMS
You need this skill if you notice ANY of these:
- Re-reading a task you already completed
- Asking a question already answered earlier in the session
- Forgetting what files you have modified
- Feeling uncertain about current task state

---

## IMMEDIATE RECOVERY STEPS

### Step 1 — Run session start
```bash
python tools/session_start.py
```
Read the full output. Do not skip any section.

### Step 2 — Check your current task
```bash
python tools/sync_state.py --status
```
This shows: what is reserved, what is done, what is blocked.

### Step 3 — Compact or clear context (Claude Code)
- `/compact` — preserves current task, compresses history
  Tell it: "compact — preserve task ID [X], files modified: [list], open decisions: [list]"
- `/clear` — only between completely unrelated tasks

### Step 4 — New session rehydration
If context is too far gone:
1. Start a new session
2. Run `python tools/session_start.py`
3. Load only the skill needed for the current task
4. Do NOT re-load skills you already used — start clean

---

## PREVENTION — do these proactively
- Load skills on demand, not upfront. One skill at a time.
- Delegate research to subagents — never research + implement in same context
- At 60% context → compact immediately, do not wait
- After 30-40 tool uses → plan to start a new session
- Commit and sync state BEFORE context gets critical

---

## CONTEXT BUDGET GUIDE
| Action | Approximate token cost |
|--------|----------------------|
| Reading AGENTS.md | ~800 tokens |
| Reading a SKILL.md | ~400-600 tokens |
| Reading MEMORY.md (150 lines) | ~1,200 tokens |
| One tool use + response | ~500-2,000 tokens |
| Full session_start.py output | ~1,500 tokens |

Load skills surgically. Every token you save is more room to implement.
