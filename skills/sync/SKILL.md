# SKILL: State Sync
# Load this file ONLY when you need to: update TASK_QUEUE.md, write to MEMORY.md,
# reserve or complete a task, or check project state.
# Do NOT load at session start — load on demand only.

---

## TASK_QUEUE.md OPERATIONS

### Reserve a task
```bash
python tools/sync_state.py TASK_ID --reserve AgentID
```
This writes your AgentID + timestamp into the Reserved field.
IF the task is already reserved by another agent → pick a different task.

### Mark a task complete
```bash
python tools/sync_state.py TASK_ID --done
```
This changes `[ ]` → `[x]` and fills in the Done timestamp.
Only run this AFTER tests pass.

### Task format reference
```markdown
- [ ] TASK_ID: Short description
    - Detail: What needs to be done
    - Priority: HIGH | MED | LOW
    - BlockedBy: NONE | OTHER_TASK_ID
    - Ref: path/to/relevant/file (optional)
    - Promise: TOKEN_ON_COMPLETION
    - Reserved: NONE | AgentID @ ISO-timestamp
    - Done: NONE | ISO-timestamp
```

---

## MEMORY.md RULES
- Hard limit: 150 lines. Prune oldest entries first when adding new ones.
- Facts about the project ONLY — never instructions, never workflow steps.
- Format: `- [YYYY-MM-DD] fact`

### What to write
```
- [DATE] lint command: ruff check .
- [DATE] test command: pytest -x
- [DATE] auth uses JWT, 24h expiry, refresh at /auth/refresh
- [DATE] conflict on auth.py during TASK_003, resolved: ours
```

### What NOT to write
- Instructions (those live in AGENTS.md and skills/)
- Workflow steps (those live in skills/)
- More than one line per fact

---

## ADDING A NEW TASK
When you discover work that needs doing but is outside your current task scope:
1. Add it to TASK_QUEUE.md under BACKLOG
2. Assign Priority and BlockedBy
3. Set Reserved: NONE
4. Do NOT start it — finish your current task first
