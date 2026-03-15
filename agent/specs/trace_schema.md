# Trace Schema — Autonomous-DNA Observability

> Designed: 2026-03-14
> Source: Research on Langfuse, Maxim AI, OpenTelemetry agent tracing patterns

## JSONL Format

One JSON object per line in `agent/traces/<session-id>.jsonl`:

```json
{
  "session_id": "string (UUID)",
  "platform": "string (antigravity|gemini-cli|claude-code|codex|unknown)",
  "timestamp": "string (ISO 8601 UTC)",
  "action": "string (session_start|reserve|plan|implement|verify|done|error|skill_load)",
  "task_id": "int | null",
  "files_touched": ["string (relative paths)"],
  "tool_count": "int | null",
  "duration_seconds": "float | null",
  "error": "string | null",
  "meta": {}
}
```

## Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | yes | UUID4 generated per agent session |
| `platform` | string | yes | Detected from `platform/ACTIVE` or `--platform` flag |
| `timestamp` | string | yes | ISO 8601 UTC timestamp |
| `action` | enum | yes | Action type being traced |
| `task_id` | int/null | no | TASK_QUEUE task ID, null for non-task actions |
| `files_touched` | list | no | Relative paths of files modified |
| `tool_count` | int/null | no | Number of tool calls (for future API-level instrumentation) |
| `duration_seconds` | float/null | no | Wall-clock time for this action |
| `error` | string/null | no | Error message if action failed |
| `meta` | dict | no | Extension dict for platform-specific data |

## Action Types

| Action | When Used |
|--------|----------|
| `session_start` | Agent starts a new session |
| `reserve` | Agent reserves a task |
| `plan` | Agent writes a plan before implementing |
| `implement` | Agent writes code |
| `verify` | Agent runs tests/validation |
| `done` | Agent marks task complete |
| `error` | An error occurred |
| `skill_load` | Agent loads a skill file |

## Storage

- Path: `agent/traces/<session-id>.jsonl`
- Current session ID: `agent/traces/.current_session`
- Target: < 200 bytes per trace entry
- Gitignored: traces should be in `.gitignore` (machine-specific)
