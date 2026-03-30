# Spec: Core Reliability & Tool Consolidation

## 1. OBJECTIVE
Consolidate `tasks.py`, `improve.py`, and `self_improve.py` into a single unified CLI for Autonomous DNA.
Ensure 100% test coverage for the core loop and task selection logic.

## 2. KEY FEATURES
- Unified `autodna` CLI (as implemented in `cli.py`).
- Reliable `next` and `mark-done` (or `complete`) commands.
- Dogfooding: The agent must use the tools it is building.

## 3. SUCCESS CRITERIA
- No duplicated functionality between `tasks.py` and `self_improve.py`.
- Automated tests pass for all tools.
