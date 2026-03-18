# TASK QUEUE
# LAST_SYNC: 2026-03-15T01:46:44Z

## IN PROGRESS

## BACKLOG
- [x] WORKTREE_AUTO_CLEAN: Auto-clean dirty worker worktrees before spawning swarm (Reserved: Codex @ 2026-03-17T04:36:24Z | BlockedBy: NONE | Priority: HIGH | Done: 2026-03-17T04:43:24Z)
- [x] HEARTBEAT_LEASE: Add task heartbeats/leases to detect active work and unblock stale blockers (Reserved: Codex @ 2026-03-17T03:59:13Z | BlockedBy: NONE | Priority: HIGH | Done: 2026-03-17T04:03:25Z)
- [x] EPOCH_AUTOFLOW: Auto research -> taskgen -> eval gate -> implement loop on `autodna epoch` (Reserved: Codex @ 2026-03-17T02:47:39Z | BlockedBy: NONE | Priority: HIGH | Done: 2026-03-17T02:55:23Z)
- [x] WORKTREE_DIRTY_AUTO: Default auto-handle dirty worker worktrees without manual intervention (Reserved: Codex @ 2026-03-16T05:34:52Z | BlockedBy: NONE | Priority: HIGH | Done: 2026-03-16T05:35:53Z)
- [x] WORKTREE_DIRTY_POLICY: Auto-handle dirty worker worktrees (keep/stash/commit) to resume runs (Reserved: Codex @ 2026-03-16T05:30:09Z | BlockedBy: NONE | Priority: HIGH | Done: 2026-03-16T05:31:07Z)
- [x] SWARM_RESUME_REBASE: Auto-resume manager/worker tasks; rebase and test before merge to avoid conflicts (Reserved: Codex @ 2026-03-16T05:19:29Z | BlockedBy: NONE | Priority: HIGH | Done: 2026-03-16T05:25:34Z)
- [x] SELF_IMPROVE_DIRTY: Handle dirty working trees in self-improve (Reserved: Codex @ 2026-03-16T05:15:45Z | BlockedBy: NONE | Priority: HIGH | Done: 2026-03-16T05:16:04Z)
- [x] SELF_IMPROVE_BOOTSTRAP: Treat completed as done, bootstrap research/taskgen/eval when queue empty (Reserved: Codex @ 2026-03-16T05:05:45Z | BlockedBy: NONE | Priority: HIGH | Done: 2026-03-16T05:09:27Z)
- [x] EVAL_TOOL: Create autodna/tools/eval.py for auto-context management (Reserved: Antigravity @ 2026-03-15T02:16:48Z | BlockedBy: NONE | Done: 2026-03-15T02:18:29Z)
- [x] CONTEXT_EVAL_HOOK: Hook autodna eval into session_start.py (Reserved: Antigravity @ 2026-03-15T02:18:30Z | BlockedBy: NONE | Done: 2026-03-15T02:18:38Z)
- [x] RESEARCH_TOOL: Create autodna/tools/research.py to query state-of-the-art agent practices (Reserved: Antigravity @ 2026-03-15T02:18:24Z | BlockedBy: NONE | Done: 2026-03-15T02:22:12Z)
- [x] EPOCH_LOOP: Implement Self-Improvement Epoch (Research -> Compare -> Eval -> Sync) logic (Reserved: Antigravity @ 2026-03-15T02:22:13Z | BlockedBy: NONE | Done: 2026-03-15T02:25:48Z)
- [x] DOGFOOD_EVAL: Add dogfooding evaluator CLI + report template to validate improvements (Reserved: Codex @ 2026-03-15T04:08:25Z | BlockedBy: NONE | Priority: MED | Done: 2026-03-15T04:10:30Z)
- [x] RESEARCH_QUALITY: Add source filters and dedupe to autodna research (Reserved: Codex @ 2026-03-15T04:17:29Z | BlockedBy: NONE | Priority: MED | Done: 2026-03-15T04:20:37Z)
- [x] EVAL_RIGOR: Add baseline vs after comparison, regression gates, and acceptance checks (Reserved: Codex @ 2026-03-15T04:25:15Z | BlockedBy: NONE | Priority: HIGH | Done: 2026-03-15T04:25:18Z)
- [x] RELIABILITY_HARDEN: Add retries/timeouts and artifact integrity checks for research/epoch (Reserved: Codex @ 2026-03-15T04:27:36Z | BlockedBy: NONE | Priority: HIGH | Done: 2026-03-15T04:31:08Z)
- [x] CONTEXT_HEALTH: Auto-prune/summarize MEMORY and prune DONE tasks safely (Reserved: Codex @ 2026-03-15T04:31:16Z | BlockedBy: NONE | Priority: HIGH | Done: 2026-03-15T04:34:54Z)
- [x] IMPROVE_LOOP: Add autodna improve command with gated apply/revert flow (Reserved: Codex @ 2026-03-15T04:39:03Z | BlockedBy: NONE | Priority: HIGH | Done: 2026-03-15T04:41:04Z)
- [x] EPOCH_IMPROVE: Wire autodna improve into epoch loop with configurable args (Reserved: Codex @ 2026-03-15T04:43:42Z | BlockedBy: NONE | Priority: HIGH | Done: 2026-03-15T04:44:26Z)
- [x] CLEAN_CODEX_CONFIG: Remove local trusted_projects entry from .codex/config.toml (Reserved: NONE | BlockedBy: NONE | Priority: MED | Done: 2026-03-15T05:15:46Z)
- [x] AUTO_SELF_IMPROVE: Run self-improve automatically during epoch without flags (Reserved: Codex @ 2026-03-15T05:12:16Z | BlockedBy: NONE | Priority: HIGH | Done: 2026-03-15T05:16:58Z)

## DONE
