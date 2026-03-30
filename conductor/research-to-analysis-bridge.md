# Plan: Autonomous Research-to-Analysis Bridge

## Objective
Enable the agent to automatically synthesize research artifacts (from `autodna/tools/research.py`) into comparative analysis reports (in `conductor/analysis/`), bridging the gap between raw data collection and actionable implementation plans.

## Implementation Steps

### 1. Update `autodna/tools/tasks.py`
- Add a utility function to check for the most recent research artifact.
- Add an `analyze` command that triggers an LLM prompt (or a simple template-filling agent task) to draft the comparative analysis based on the template.

### 2. Update `autodna/tools/epoch.py`
- Integrate a new `analysis` step in the epoch loop. 
- The step should:
    - Look for the latest research artifact.
    - Check if a corresponding analysis report exists in `conductor/analysis/`.
    - If not, invoke the new `analyze` tool to generate one.

### 3. Create Automated Analysis Tool
- Create `autodna/tools/analyze.py`:
    - Read `conductor/analysis-template.md`.
    - Read the latest research artifact.
    - Draft a "Comparative Analysis Report" filling out the template sections.
    - Save it to `conductor/analysis/latest_analysis.md`.

## Verification
- Run `epoch.py`. It should now:
    1. Research online.
    2. Detect the new artifact.
    3. Generate the analysis report automatically.
    4. Proceed to the Improvement phase.
