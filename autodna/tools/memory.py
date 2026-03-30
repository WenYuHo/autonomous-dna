import os
import sys
import json
import re
from pathlib import Path
from datetime import datetime, timezone

try:
    from aura_memory import Memory
except ImportError:
    # Fallback if not installed correctly in some environments
    Memory = None

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from autodna.tools.io_utils import read_text_fallback

MEMORY_DB_PATH = Path("agent/brain.aura")
LEGACY_MEMORY_FILE = Path("agent/MEMORY.md")

class IntelligentMemory:
    def __init__(self, db_path=MEMORY_DB_PATH):
        self.db_path = db_path
        self.memory = None
        if Memory:
            self.memory = Memory(str(db_path))

    def add_fact(self, content: str, source: str = "agent", trust: float = 0.8):
        """Adds a fact to the structured memory."""
        if self.memory:
            # Aura handles deduplication and consolidation internally
            self.memory.add(content, trust=trust, metadata={"source": source})
        
        # Always append to legacy file for human readability and safety
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        fact_line = f"- [{timestamp}] [{source.upper()}] {content}\n"
        
        with open(LEGACY_MEMORY_FILE, "a", encoding="utf-8") as f:
            f.write(fact_line)

    def retrieve_relevant(self, query: str, limit: int = 10) -> list[str]:
        """Retrieves only the facts relevant to the query."""
        if not self.memory:
            # Fallback to simple keyword search in legacy file
            if not LEGACY_MEMORY_FILE.exists():
                return []
            content = read_text_fallback(LEGACY_MEMORY_FILE)
            facts = re.findall(r"^- .*", content, re.MULTILINE)
            # Very basic keyword match
            keywords = query.lower().split()
            relevant = [f for f in facts if any(kw in f.lower() for kw in keywords)]
            return relevant[:limit]

        # Use Aura's cognitive retrieval
        results = self.memory.query(query, limit=limit)
        return [r.content for r in results]

    def migrate_legacy(self):
        """One-time migration from MEMORY.md to Aura."""
        if not LEGACY_MEMORY_FILE.exists() or not self.memory:
            return
        
        content = read_text_fallback(LEGACY_MEMORY_FILE)
        facts = re.findall(r"^- \[(.*?)\] \[(.*?)\] (.*)", content)
        for ts, source, fact in facts:
            self.memory.add(fact, trust=0.9, metadata={"date": ts, "source": source})
        print(f"Migrated {len(facts)} facts to Aura cognitive memory.")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Autonomous DNA Intelligent Memory")
    parser.add_argument("action", choices=["add", "query", "migrate"])
    parser.add_argument("text", nargs="?", help="Fact to add or query to search")
    parser.add_argument("--source", default="agent")
    parser.add_argument("--trust", type=float, default=0.8)
    
    args = parser.parse_args()
    im = IntelligentMemory()
    
    if args.action == "add":
        if not args.text:
            print("Error: Text required for add")
            sys.exit(1)
        im.add_fact(args.text, args.source, args.trust)
        print("Fact added.")
    elif args.action == "query":
        if not args.text:
            print("Error: Query text required")
            sys.exit(1)
        results = im.retrieve_relevant(args.text)
        for r in results:
            print(r)
    elif args.action == "migrate":
        im.migrate_legacy()

if __name__ == "__main__":
    main()
