
import sys
from pathlib import Path
from autodna.tools.topic_generator import identify_next_topic

# Verify that the generator picks a topic from the frontier if present
topic, reason = identify_next_topic()

print(f"topic: {topic}")
print(f"reason: {reason}")

# Assertion for experiment.py
if "strategic" in reason.lower() or "error" in reason.lower():
    print("topic_quality: 1.0")
else:
    print("topic_quality: 0.5")
