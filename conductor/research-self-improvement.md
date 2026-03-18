# Research Plan: Self-Improvement Loop Audit

## Objective
Identify gaps, inefficiencies, or missing logic in the current autonomous self-improvement loop (`tools/self_improve.py` and `autodna/tools/tasks.py`) to ensure continuous, high-quality autonomous development.

## Scope
- Analyze the orchestration logic in `tools/self_improve.py`.
- Audit the task lifecycle in `autodna/tools/tasks.py` (claim, heartbeat, complete, fail).
- Verify the integration between the task queue and the autonomous loop.
- Assess the error handling and retry mechanism for autonomous tasks.

## Research Steps
1. **Analyze Loop Orchestration:** Examine `tools/self_improve.py` and its dependencies (e.g., `autodna/tools/taskgen.py`, `autodna/tools/epoch.py`) to understand how the loop triggers, executes tasks, and validates results.
2. **Audit Task Lifecycle:** Review `autodna/tools/tasks.py` for robustness. Are there edge cases in task claims or status updates that could cause deadlocks?
3. **Cross-Check with AGENTS.md:** Compare the observed loop behavior against the "CORE LOOP" and "HARD RULES" defined in `AGENTS.md`.
4. **Identify Gaps:**
   - Are there missing metrics or observability logs?
   - Is the heartbeat mechanism properly utilized to prevent stale task execution?
   - Is there a clear path for "Failed" tasks to be reviewed by a human?
   - Are environment variables (e.g., `AUTODNA_SELF_IMPROVE_GATES`) being applied consistently?

## Expected Deliverables
- A summary of the current self-improvement loop's architecture.
- A list of identified gaps or areas for improvement.
- A proposed action plan to bridge these gaps.
