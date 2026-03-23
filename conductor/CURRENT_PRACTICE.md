# CURRENT PRACTICE: Autonomous DNA Standards
# This document tracks our selected approaches, rationale, and rejected alternatives.
# Update this file AFTER every successful EXPERIMENT to avoid redundant research.

---

## 1. CORE DOMAINS

### [WEB RESEARCH]
- **Current Standard:** `autodna research` via **agent-browser** (Vercel Labs).
- **Status:** **ACTIVE**.
- **Discovery Logic:** **Dynamic Topic Selection** via `topic_generator.py` (Cycle #21, 2026-03-20).
- **Rationale:** Prioritizes strategic goals from "Research Frontier" and autonomously reacts to internal "Pain" (error patterns in TASK_QUEUE).
- **Engines:** Google (Default), Perplexity (Technical/Deep).

### [SELF-EVOLUTION / IMPROVEMENT]
- **Current Standard:** **Karpathy-style Gated Loops** via `experiment.py`.
- **Rationale:** Deterministic 5-minute time budget. Empirical evidence (metrics/assertions) beats "architectural vibes."
- **Gating Logic:** Mandatory **Assertions** (Claude-style) + Metric Deltas (e.g., `signal_score >= baseline`).
- **Rejected:** 
    - *Sequential Vibes Check:* Agents just "thinking" it's better without proof leads to regression.

### [MEMORY MANAGEMENT]
- **Current Standard:** **Cognitive Retrieval** via `memory.py` + **Aura**.
- **Status:** **CERTIFIED** (Cycle #20, 2026-03-20).
- **Rationale:** Proven 98% reduction in session-start tokens. Replaces flat `MEMORY.md` dump with progressive disclosure.
- **Enforcement:** Integrated into `tools/session_start.py`.

### [TASK ORCHESTRATION]
- **Current Standard:** **Deterministic Research Protocol** (`research_protocol.py`).
- **Rationale:** Encodes methodology into a state machine. Prevents skipping steps (Plan -> Discover -> Analyze -> Evolve).
- **Rejected:** 
    - *Markdown Workflows:* Too easy for agents to ignore or "drift" from when the context gets crowded.

### [SECURITY VETTING]
- **Current Standard:** **Static Analysis Gate** (`security_scan.py`).
- **Status:** **ACTIVE**.
- **Rationale:** Automatically flags injection risks (`shell=True`, `eval`, `exec`) before any code is evolved.
- **Enforcement:** Mandatory stage in `ResearchProtocol`.

---

## 2. ARCHITECTURAL DECISIONS

| ID | Decision | Standard | Date |
|----|----------|----------|------|
| ADR-001 | Browser Automation | `agent-browser` CLI | 2026-03-20 |
| ADR-002 | Improvement Loop | Gated Experiment Runner | 2026-03-20 |
| ADR-003 | Metric Collection | Stdout `KEY: VALUE` Parsing | 2026-03-20 |
| ADR-004 | Security Gate | AST-Based Injection Scan | 2026-03-20 |

---

## 3. RESEARCH FRONTIER (Next Steps)
- **Context Compression:** Researching "Context Forking" to isolate skill execution.
- **LLM-as-a-Judge:** Integrating specialized "Grader" agents for multi-agent evaluation (Claude 2.0 pattern).
- **Persistent Memory:** Moving from flat `MEMORY.md` to a vector-indexed or structured knowledge graph.
