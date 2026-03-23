# Plan: Enforcing Research-First Autonomous Evolution

## Objective
Slow down the autonomous loop and force a strict "Research -> Comparative Analysis -> Plan -> Implement" workflow. Current agents are skipping the research and analysis phases.

## Changes Required

### 1. Update `tools/epoch.py`
- Enforce that the Research phase must succeed and produce an artifact that is manually (or programmatically) reviewed before the Improve phase is permitted to run.
- Add a new "Analysis" phase in the epoch.

### 2. Update `tools/self_improve.py`
- Modify the command structure to ensure it requires an explicit task plan from the `TASK_QUEUE.json` that references a valid research artifact.
- Add a "Pre-flight Check" that validates the research artifact content before proceeding with any code implementation.

### 3. Repository Governance
- Add a new required folder `conductor/analysis/` for storing Comparative Analysis Reports.
- Update `AGENTS.md` to define a "Deep Research" protocol that prohibits code changes unless a Comparative Analysis Report (linking to research and current implementation) is present.

## Implementation Steps
1. **Define Analysis Format**: Create `conductor/analysis-template.md` (Research Summary + Current Implementation + Comparative Benchmarking + Proposed Plan).
2. **Update Epoch Loop**: Modify `autodna/tools/epoch.py` to check for `conductor/analysis/` files.
3. **Task Queue Enforcement**: Update `autodna/tools/tasks.py` so the `[IMPROVE]` tasks in `TASK_QUEUE.json` are automatically `blocked` if they do not link to an approved analysis report.
4. **Research Artifact Review**: Update `autodna/tools/research.py` to force-require a summary/comparison step before completion.

## Verification
- Run `epoch.py` and verify it halts if no research analysis is performed.
- Manually trigger a research task and verify the agent must create an analysis report before it can claim an improvement task.
