# Token Burn Metrics Design

## 1. Goal
To build a system that accurately measures and compares the efficiency (tokens, time, and steps) of different autonomous AI clients (Gemini CLI, Claude Code, Aider) as they repeatedly dogfood the `Autonomous-DNA` repository.

## 2. Supported AI CLI Analysis
Different command-line AI agents report token usage differently. Since `Autonomous-DNA` orchestrates these headlessly via `autodna start`, extracting token usage reliably is a challenge:

- **Aider**: Reports token usage continuously at the end of sessions/API calls in the stdout stream (e.g., `Tokens: 4.5k sent, 2.1k received`).
- **Claude Code**: Shows interactive token usage, but in headless mode (via `-p`) token usage might not be explicitly piped to stdout unless using a verbose flag. A local `.claude` history directory usually contains API logs.
- **Gemini CLI**: Does not natively output robust token count summaries in stdout unless wrapped or run with specific verbose flags. Outputs quota limit warnings.

### Conclusion on Approach
To create a universal benchmark, our core metrics must rely on what we can observe at the orchestrator (trace logger) level, rather than exclusively parsing stdout for API tokens.

## 3. Core Metrics to Measure

We will evaluate efficiency through the following metrics in `eval_token_burn.py`:

| Metric | Source | Description |
|--------|--------|-------------|
| `time_per_task` | `trace_logger.py` (Duration) | Total wall-clock time from task assignment to task completion/error. |
| `tools_per_task` | `trace_logger.py` | Count of tools called. High tool counts usually correlate with high token waste (overly talkative or confused agents). |
| `files_per_task` | `trace_logger.py` | Count of distinct files touched. Measures directness of implementation. |
| `retries_per_task` | `agent_runner.py` (Exit Code/Loop) | How many times the swarm crashed or failed tests and had to retry. |
| `estimated_prompt_burn` | Derived from Task Queue + Tool sum | Since exact token counts are obscured by CLI boundaries, we estimate prompt burn dynamically by multiplying the `tool_count` by the average repository context size (e.g., 50k tokens per round trip). |

## 4. Required Implementation Changes for Task 202

To build `eval_token_burn.py`, we need the following:

1. **Input Data**: The existing `agent/traces/*.jsonl` files already capture `duration_seconds`, `tool_count`, and `files_touched`.
2. **Evaluation Tool**: `eval_token_burn.py` will read the JSONL files, group them by `task_id`, and sum the metrics.
3. **The `--baseline` Flag**: The tool will write `agent/reports/baseline_metrics.json` to store current cycle metrics. When run again in later cycles, it will compare the new runs against the baseline to prove if the self-improvement loop made the code easier (cheaper) to work with.

## 5. Summary
We will prioritize orchestrator-level traces (time, tools, files) as the primary proxy for token burn, as extracting perfect API-level tokens across three different open-source CLI agents requires fragile regex parsing and frequent updates.
