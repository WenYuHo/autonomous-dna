# Plan: Core Reliability & Tool Consolidation

## [x] P0: Initialize Track and Registry
- [x] Create `conductor/tracks.md`.
- [x] Create `conductor/tracks/1-core-reliability/spec.md`.
- [x] Create `conductor/tracks/1-core-reliability/plan.md`.

## [ ] P1: Consolidate `tasks.py` and `self_improve.py`
- [ ] Implement `next` and `mark-done` directly into `autodna/tools/tasks.py`.
- [ ] Update `self_improve.py` to be a wrapper or alias for the unified commands.
- [ ] Add unit tests for the consolidated commands.

## [ ] P2: Documentation & Sync
- [ ] Update `AGENTS.md` to reflect the unified CLI commands if they changed.
- [ ] Sync the `TASK_QUEUE.json` with the new track tasks.
