# TASK QUEUE
# LAST_SYNC: 2026-03-15T01:28:00Z

## IN PROGRESS

## BACKLOG

- [ ] BOOTSTRAP_SCRIPT: Create scripts/bootstrap.py installer.
    - Detail: README references `scripts/bootstrap.py` but it doesn't exist. Create it to auto-generate missing scaffold files (platform configs, hooks, skill stubs). Must be idempotent.
    - Priority: HIGH
    - BlockedBy: NONE
    - Promise: BOOTSTRAP_WORKS
    - Reserved: NONE
    - Done: NONE

- [ ] TEST_AGENT_RUNNER: Add unit tests for autodna/core/agent_runner.py.
    - Detail: Mock subprocess.Popen, test model fallback on quota exhaustion, test retry logic on crash, test clean exit. Target 80%+ coverage.
    - Priority: HIGH
    - BlockedBy: NONE
    - Promise: AGENT_RUNNER_TESTED
    - Reserved: NONE
    - Done: NONE

- [ ] TEST_ENGINE_START: Add unit tests for autodna/core/engine_start.py.
    - Detail: Mock subprocess calls. Test worktree setup, junction creation, headless vs interactive launch, log file creation.
    - Priority: MED
    - BlockedBy: NONE
    - Promise: ENGINE_START_TESTED
    - Reserved: NONE
    - Done: NONE

- [ ] PLATFORM_CONFIGS: Add missing platform config files.
    - Detail: Create `.antigravity/rules.md`, `.codex/config.toml` with sensible defaults. These are flagged missing by bridge.py validation.
    - Priority: MED
    - BlockedBy: NONE
    - Promise: PLATFORM_CONFIGS_PRESENT
    - Reserved: NONE
    - Done: NONE

- [ ] ERROR_HANDLING: Improve CLI error handling and user messaging.
    - Detail: `autodna start` should check if git is initialized, if worktrees exist before creating, and print actionable errors. `cli.py` should catch ImportError if tools are broken.
    - Priority: MED
    - BlockedBy: NONE
    - Promise: ERRORS_HANDLED
    - Reserved: NONE
    - Done: NONE

## DONE

- [x] CLI_STANDARDIZATION: Port and standardize the global CLI layout.
    - Done: 2026-03-15T00:46:04Z

- [x] TOKEN_BENCHMARK: Implement a token burn benchmark utility.
    - Done: 2026-03-15T00:49:34Z

- [x] INITIAL_SETUP: Verify scaffold and define first real task.
    - Done: 2026-03-15T00:41:20Z

- [x] DOGFOOD_INFRA: Add CI pipeline, test coverage, main/dev branching.
    - Done: 2026-03-15T01:22:00Z
