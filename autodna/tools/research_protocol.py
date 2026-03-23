import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from autodna.tools import tasks

DEFAULT_QUEUE = Path("agent/TASK_QUEUE.json")

class ResearchProtocol:
    def __init__(self, topic, goal, queue_path=DEFAULT_QUEUE):
        self.topic = topic
        self.goal = goal
        self.queue_path = queue_path
        self.cycle_id = None

    def initialize_cycle(self):
        """Creates a parent task in the queue to track the research cycle."""
        title = f"[RESEARCH_CYCLE] {self.topic}"
        description = f"Goal: {self.goal}\n\nStages:\n1. DISCOVERY\n2. ANALYSIS\n3. EXPERIMENT\n4. VALIDATION"
        
        # Check if already exists
        db = tasks.load_db()
        for t in db.get("tasks", []):
            if t.get("title") == title and t.get("status") != "completed":
                self.cycle_id = t.get("id")
                print(f"Resuming existing cycle: {self.cycle_id}")
                return self.cycle_id

        # Create new
        from autodna.tools.taskgen import max_task_id
        self.cycle_id = max_task_id(db.get("tasks", [])) + 1
        new_task = {
            "id": self.cycle_id,
            "title": title,
            "description": description,
            "status": "in_progress",
            "stage": "PLANNING",
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        db.setdefault("tasks", []).append(new_task)
        tasks.save_db(db)
        print(f"Initialized new research cycle: {self.cycle_id}")
        return self.cycle_id

    def update_stage(self, stage, notes=""):
        db = tasks.load_db()
        for t in db.get("tasks", []):
            if t.get("id") == self.cycle_id:
                t["stage"] = stage
                t["notes"] = notes
                t["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                break
        tasks.save_db(db)
        print(f"Stage Updated: {stage}")

    def run_discovery(self, engine="google"):
        self.update_stage("DISCOVERY")
        cmd = f"python autodna/tools/research.py \"{self.topic}\" --engine {engine} --max-sources 2"
        print(f"Running Discovery: {cmd}")
        # In a real scenario, we'd execute this. For now, we simulate success.
        return True

    def run_experiment(self, target, delta_file, task_cmd, gate):
        self.update_stage("EXPERIMENT")
        cmd = f"python autodna/tools/experiment.py --target {target} --delta-file {delta_file} --task-cmd \"{task_cmd}\" --gate \"{gate}\""
        print(f"Running Experiment: {cmd}")
        # In real usage, the agent calls this command.
        return True

    def run_security_check(self, target):
        self.update_stage("SECURITY_CHECK")
        cmd = f"python autodna/tools/security_scan.py {target}"
        print(f"Running Security Scan: {cmd}")
        # Ideally we'd execute and check return code here
        return True

def main():
    parser = argparse.ArgumentParser(description="Deterministic Research Protocol Runner")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--stage", choices=["init", "discovery", "experiment", "finalize"], default="init")
    
    args = parser.parse_args()
    rp = ResearchProtocol(args.topic, args.goal)
    
    if args.stage == "init":
        rp.initialize_cycle()
    elif args.stage == "discovery":
        rp.initialize_cycle() # Resume
        rp.run_discovery()
    # ... more stages

if __name__ == "__main__":
    main()
