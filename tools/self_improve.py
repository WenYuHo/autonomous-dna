"""
tools/self_improve.py
Unified wrapper for Autonomous-DNA tasks API.
"""

import sys
import os
import json

# Ensure project root is in path to allow importing autodna
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autodna.tools import tasks

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Autonomous DNA Self-Improvement Bridge")
    parser.add_argument("action", choices=["next", "mark-done", "mark-error"])
    parser.add_argument("--id", type=int, help="Task ID")
    parser.add_argument("--notes", help="Optional completion/error notes")
    args = parser.parse_args()

    if args.action == "next":
        task = tasks.get_next_task()
        if task:
            print(json.dumps(task))
        else:
            print("null")
    elif args.action == "mark-done":
        if not args.id:
            print("ERROR: --id required for mark-done")
            sys.exit(1)
        tasks.complete_task(args.id, args.notes)
    elif args.action == "mark-error":
        if not args.id:
            print("ERROR: --id required for mark-error")
            sys.exit(1)
        tasks.fail_task(args.id, args.notes)

if __name__ == "__main__":
    main()
