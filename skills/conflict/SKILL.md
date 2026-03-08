# SKILL: Conflict Resolution
# Load this file ONLY when you encounter a merge conflict during git operations.
# Do NOT load at session start — load on demand only.

---

## AUTOMATIC RESOLUTION RULES

Apply these in order. Do not deviate.

| File type | Resolution |
|-----------|-----------|
| Lock files (`*.lock`, `package-lock.json`, `poetry.lock`) | Take theirs |
| Generated files (`*.pb.go`, `dist/`, `build/`) | Take theirs |
| Scaffold files (AGENTS.md, CLAUDE.md etc.) | STOP — notify human |
| All other files | Take ours |

---

## STEP BY STEP

```bash
git rebase origin/main
# For each conflict:
git checkout --theirs <lock-or-generated-file>   # lock/generated files
git checkout --ours <any-other-file>              # everything else
git add <file>
git rebase --continue
```

---

## LOGGING — required for every conflict
After resolving, add to MEMORY.md:
```
- [YYYY-MM-DD] conflict on <FILE> during <TASK_ID>, resolution: ours/theirs/human
```

---

## ESCALATION — after 3 failed attempts
1. Run: `git rebase --abort`
2. Log in MEMORY.md: `- [DATE] unresolvable conflict on TASK_ID after 3 attempts`
3. Update TASK_QUEUE.md: mark task as Blocked, add note
4. Notify human — include: which files conflict, what you tried, git log output

Do NOT attempt a 4th time. Do NOT force-push.
