# SKILL: Research
# Load this file ONLY when you need to research a library, API, pattern, or technology.
# Do NOT load at session start — load on demand only.

---

## RESEARCH PROTOCOL

### Step 1 — Check MEMORY.md first
Before searching anywhere, scan MEMORY.md for an existing entry on this topic.
IF a relevant entry exists → use it. Do NOT re-research what is already known.

### Step 2 — Delegate to subagent (Claude Code)
```
"Use the researcher subagent to find how X handles Y"
```
The subagent searches and returns a summary. It does NOT edit any files.
You receive the summary and continue.

### Step 3 — Direct search (Gemini CLI / other platforms)
Use web search or MCP tools to find current documentation.
Prefer: official docs, GitHub READMEs, release notes.
Avoid: blog posts, tutorials older than 12 months, StackOverflow for version-specific questions.

### Step 4 — Log the finding
Add to MEMORY.md immediately after researching:
```
- [YYYY-MM-DD] researched <topic>: <one-line summary of finding>
- [YYYY-MM-DD] <library> version <X>: key API is <Y>, docs at <URL>
```

---

## NEVER IMPLEMENT WHILE RESEARCHING
Research and implementation are separate context windows.
IF you are in a research phase → return a summary only, do NOT write code.
Start a fresh task for implementation.

---

## WHEN TO STOP RESEARCHING
- You have enough to write a test
- You have found the official API signature
- You have confirmed version compatibility
Do NOT continue researching once you have enough to proceed.
