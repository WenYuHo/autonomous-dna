# SKILL: Git Operations
# Load this file ONLY when you need to: commit, open PRs, rebase, merge, or resolve conflicts.
# Do NOT load at session start — load on demand only.

---

## FULL AUTONOMOUS GIT FLOW

```
commit
  → open PR
    → CI passes        → squash merge + delete branch ✓
    → behind main      → rebase → auto-resolve conflicts → re-push → retry PR
    → CI fails         → log in MEMORY.md → notify human ⚠️
    → unresolvable (3x) → log → notify human ⚠️
```

---

## ONE COMMAND — does everything
```bash
python tools/git_ops.py TASK_ID full "describe what you did"
```

---

## STEP BY STEP — if needed
```bash
python tools/git_ops.py TASK_ID init            # create branch from main
python tools/git_ops.py TASK_ID commit "msg"    # stage, commit, push
python tools/git_ops.py TASK_ID pr              # open PR (rebases if behind)
python tools/git_ops.py TASK_ID merge <pr_url>  # monitor CI + auto-merge
```

---

## CONFLICT RESOLUTION — automatic rules
- Lock files and generated files → take theirs
- All other files → take ours
- Log every conflict in MEMORY.md: `- [DATE] conflict on FILE during TASK_ID, resolution: ours/theirs`
- After 3 failed attempts → STOP. Log. Notify human.

---

## BRANCH NAMING
```
feat/TASK_ID-short-description
fix/TASK_ID-short-description
chore/TASK_ID-short-description
```

---

## COMMIT MESSAGE FORMAT
```
type(scope): short description

- what changed
- why it changed
- TASK_ID: TASK_ID
```

---

## YOU ONLY NOTIFY THE HUMAN WHEN
- CI fails and you cannot fix it yourself
- Conflicts cannot be resolved after 3 attempts
- A force-push to a protected branch would be required
