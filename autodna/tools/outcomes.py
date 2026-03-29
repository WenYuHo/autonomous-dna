import json
from pathlib import Path
from datetime import datetime, timezone

def record_outcome(task_id: int, status: str, notes: str, agent_name: str, outcomes_dir: Path):
    """Saves a task outcome to JSON for analysis."""
    outcomes_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename for this run
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"task_{task_id}_{timestamp}.json"
    filepath = outcomes_dir / filename
    
    data = {
        "task_id": task_id,
        "status": status,
        "notes": notes,
        "agent": agent_name,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    
    filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return filepath
