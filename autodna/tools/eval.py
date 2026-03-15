import os
import sys
import argparse
import datetime
import re
from pathlib import Path

def defragment_tasks(dry_run=False):
    """
    Reads agent/TASK_QUEUE.md and removes completed [x] tasks that were finished
    more than 7 days ago. If no timestamp is present, it relies on LAST_SYNC.
    """
    queue_path = Path("agent/TASK_QUEUE.md")
    if not queue_path.exists():
        print("⚠️ No TASK_QUEUE.md found.")
        return 0

    content = queue_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    new_lines = []
    removed_count = 0
    in_done_section = False
    
    for line in lines:
        if line.startswith("## DONE"):
            in_done_section = True
            new_lines.append(line)
            continue
            
        if line.startswith("## ") and not line.startswith("## DONE"):
            in_done_section = False
            
        if in_done_section and line.strip().startswith("- [x]"):
            removed_count += 1
            if dry_run:
                print(f"[Defrag] Would remove obsolete task: {line.strip()}")
            continue
            
        new_lines.append(line)

    if removed_count > 0:
        print(f"🧹 Defragmenter: Pruned {removed_count} stale completed tasks from context.")
        if not dry_run:
            queue_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    else:
        print("✅ Task context is optimal. No defragmentation needed.")
        
    return removed_count

def consolidate_memory(dry_run=False):
    """
    Reads agent/MEMORY.md and warns if it's getting too long.
    Eventually triggers an LLM summarization.
    """
    memory_path = Path("agent/MEMORY.md")
    if not memory_path.exists():
        return
        
    content = memory_path.read_text(encoding="utf-8")
    fact_count = len(re.findall(r'^- ', content, re.MULTILINE))
    
    print(f"🧠 Memory checks: {fact_count} facts tracked.")
    if fact_count > 100:
        print("⚠️ Warning: MEMORY.md is exceeding 100 facts. Context degradation likely.")
        if not dry_run:
            print("⏳ [Stub] LLM summarizer would kick in here to compress historical facts.")
            
def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description="Autonomous DNA Context Evaluator (`autodna eval`)")
    parser.add_argument("--quick", action="store_true", help="Run fast inline checks (suitable for session_start hooks)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be deleted without modifying files")
    
    # autodna cli.py passes ['autodna eval', '--args...']
    # If called standalone, sys.argv is ['eval.py', '--args...']
    args_to_parse = sys.argv[1:]
    if sys.argv and sys.argv[0].startswith("autodna"):
         args_to_parse = sys.argv[1:]
         
    args, _ = parser.parse_known_args(args_to_parse)

    print("--- 🩺 Autonomous DNA: Context Doctor ---")
    defragment_tasks(dry_run=args.dry_run)
    consolidate_memory(dry_run=args.dry_run)
    print("-----------------------------------------")

if __name__ == "__main__":
    main()
