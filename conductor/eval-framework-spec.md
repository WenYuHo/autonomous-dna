# Evaluation Framework Specification

## 1. Goal
Provide a quantitative and qualitative method to compare agent implementation approaches.

## 2. Report Format (JSON)
```json
{
  "timestamp": "YYYY-MM-DDTHH:MM:SSZ",
  "baseline_label": "old_method",
  "after_label": "new_method",
  "metrics": {
    "token_usage": {"baseline": 1234, "after": 1000},
    "latency_seconds": {"baseline": 5.2, "after": 4.1},
    "success_rate": {"baseline": 0.8, "after": 0.9}
  },
  "notes": "Qualitative comparison and recommendation."
}
```

## 3. Evaluation Flow
1. **Prepare:** Run benchmark workflow with existing pattern.
2. **Apply:** Run new agent approach.
3. **Compare:** Use `autodna.tools.eval` to diff artifacts and generate the report.
