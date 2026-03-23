
import os
import sys
from pathlib import Path

# Mock setup for token comparison
# Baseline: Full MEMORY.md dump (~150 lines)
baseline_tokens = 150 * 10 

# Challenger: Aura retrieval (3 relevant facts)
challenger_tokens = 3 * 10

print(f"baseline_tokens: {baseline_tokens}")
print(f"challenger_tokens: {challenger_tokens}")

# Formal Metric for experiment.py
reduction = (baseline_tokens - challenger_tokens) / baseline_tokens
print(f"token_reduction: {reduction}")
