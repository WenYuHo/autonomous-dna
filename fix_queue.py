import json
from pathlib import Path

p = Path("agent/TASK_QUEUE.json")
try:
    # Try reading with BOM
    content = p.read_text(encoding="utf-8-sig")
    data = json.loads(content)
except Exception:
    try:
        # Try standard utf-8
        content = p.read_text(encoding="utf-8")
        data = json.loads(content)
    except Exception as e:
        print(f"Failed to read queue: {e}")
        exit(1)

# Write back as clean UTF-8 (no BOM)
p.write_text(json.dumps(data, indent=2), encoding="utf-8")
print("Queue fixed.")
