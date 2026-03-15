import sys
import argparse
import datetime
import re
from pathlib import Path

def parse_iso_timestamp(value: str):
    try:
        cleaned = value.strip()
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        return datetime.datetime.fromisoformat(cleaned)
    except Exception:
        return None


def defragment_tasks(dry_run=False, older_than_days=7, now=None):
    """
    Reads agent/TASK_QUEUE.md and removes completed [x] tasks that were finished
    more than older_than_days ago. If no Done timestamp is present, it falls back
    to LAST_SYNC (if available).
    """
    queue_path = Path("agent/TASK_QUEUE.md")
    if not queue_path.exists():
        print("âš ï¸ No TASK_QUEUE.md found.")
        return 0

    content = queue_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    last_sync = None
    for line in lines:
        if line.startswith("# LAST_SYNC:"):
            last_sync = parse_iso_timestamp(line.split(":", 1)[1].strip())
            break

    now_dt = now or datetime.datetime.now(datetime.UTC)
    cutoff = now_dt - datetime.timedelta(days=older_than_days)

    new_lines = []
    removed_count = 0

    for line in lines:
        if not line.strip().startswith("- [x]"):
            new_lines.append(line)
            continue

        done_match = re.search(r"Done:\s*([0-9TZ:+-]+)", line)
        done_dt = parse_iso_timestamp(done_match.group(1)) if done_match else None
        effective_dt = done_dt or last_sync

        if effective_dt and effective_dt < cutoff:
            removed_count += 1
            if dry_run:
                print(f"[Defrag] Would remove obsolete task: {line.strip()}")
            continue

        new_lines.append(line)

    if removed_count > 0:
        print(f"ðŸ§¹ Defragmenter: Pruned {removed_count} stale completed tasks from context.")
        if not dry_run:
            queue_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    else:
        print("âœ… Task context is optimal. No defragmentation needed.")

    return removed_count


def consolidate_memory(dry_run=False, max_facts=100, prune=False, archive_path=Path("agent/MEMORY_ARCHIVE.md")):
    """
    Reads agent/MEMORY.md and warns if it's getting too long.
    Optionally prunes oldest facts and archives them.
    """
    memory_path = Path("agent/MEMORY.md")
    if not memory_path.exists():
        return

    content = memory_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    header_lines = []
    facts = []
    for line in lines:
        if line.startswith("- "):
            facts.append(line)
        else:
            header_lines.append(line)

    fact_count = len(facts)
    print(f"ðŸ§  Memory checks: {fact_count} facts tracked.")
    if fact_count <= max_facts:
        return

    print("âš ï¸ Warning: MEMORY.md is exceeding max facts. Context degradation likely.")
    if not prune:
        return

    keep = facts[-max_facts:]
    pruned = facts[:-max_facts]
    if dry_run:
        print(f"[Memory] Would prune {len(pruned)} facts.")
        return

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    archive_header = f"# Archived on {archive_stamp}"
    archive_content = "\n".join([archive_header, *pruned, ""])
    with archive_path.open("a", encoding="utf-8") as handle:
        handle.write(archive_content + "\n")

    header_block = "\n".join(header_lines).rstrip()
    if header_block:
        header_block += "\n"
    memory_path.write_text(header_block + "\n".join(keep) + "\n", encoding="utf-8")


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description="Autonomous DNA Context Evaluator (`autodna eval`)")
    parser.add_argument("--quick", action="store_true", help="Run fast inline checks (suitable for session_start hooks)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be deleted without modifying files")
    parser.add_argument("--prune-done-days", type=int, default=7, help="Prune completed tasks older than N days")
    parser.add_argument("--prune-memory", action="store_true", help="Prune MEMORY.md if over cap and archive")
    parser.add_argument("--memory-cap", type=int, default=100, help="Max facts to keep in MEMORY.md")
    parser.add_argument("--memory-archive", default="agent/MEMORY_ARCHIVE.md", help="Archive path for pruned facts")

    # autodna cli.py passes ['autodna eval', '--args...']
    # If called standalone, sys.argv is ['eval.py', '--args...']
    args_to_parse = sys.argv[1:]
    if sys.argv and sys.argv[0].startswith("autodna"):
         args_to_parse = sys.argv[1:]

    args, _ = parser.parse_known_args(args_to_parse)

    print("--- ðŸ©º Autonomous DNA: Context Doctor ---")
    defragment_tasks(dry_run=args.dry_run, older_than_days=args.prune_done_days)
    consolidate_memory(
        dry_run=args.dry_run,
        max_facts=args.memory_cap,
        prune=args.prune_memory,
        archive_path=Path(args.memory_archive),
    )
    print("-----------------------------------------")

if __name__ == "__main__":
    main()
