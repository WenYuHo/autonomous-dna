import sys
import argparse
from pathlib import Path

# Fix Windows cp1252 encoding for emoji output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DOCS = {
    "memory": "agent/MEMORY.md",
    "architecture": "agent/ARCHITECTURE.md",
    "map": "agent/CODEBASE_MAP.md",
    "decisions": "agent/DECISIONS.md",
    "lessons": "agent/LESSONS.md",
    "tech-stack": "conductor/tech-stack.md",
    "workflow": "conductor/workflow.md",
}

def get_doc(topic):
    if topic in DOCS:
        p = Path(DOCS[topic])
        if p.exists():
            print(f"--- 📖 CONTENT OF {topic.upper()} ---")
            print(p.read_text(encoding="utf-8"))
        else:
            print(f"❌ Document for '{topic}' not found at {DOCS[topic]}")
    else:
        print(f"❌ Unknown topic: {topic}")
        print("Run 'python tools/symphony_context.py list' to see available topics.")

def list_docs():
    print("📚 Available Documentation Topics:")
    for key, path in DOCS.items():
        size = "Unknown"
        p = Path(path)
        if p.exists():
            size = f"{p.stat().st_size:,} bytes"
        print(f"  - {key:15s} ({size}) -> {path}")

def main():
    parser = argparse.ArgumentParser(description="Symphony Context/Memory CLI Tool")
    subparsers = parser.add_subparsers(dest="action", help="Action to perform")

    # List
    subparsers.add_parser("list", help="List available documentation topics")

    # Get
    parser_get = subparsers.add_parser("get", help="Fetch context for a specific topic")
    parser_get.add_argument("topic", help="The topic to retrieve (e.g., 'map', 'memory')")

    args = parser.parse_args()

    if args.action == "list":
        list_docs()
    elif args.action == "get":
        get_doc(args.topic)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
