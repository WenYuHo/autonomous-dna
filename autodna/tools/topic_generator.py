import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from autodna.tools import tasks
from autodna.tools.io_utils import read_text_fallback

def identify_next_topic():
    print("--- 🧠 Dynamic Topic Generator ---")
    
    # 1. ANALYZE INTERNAL PAIN (Errors)
    db = tasks.load_db()
    recent_errors = [t for t in db.get("tasks", []) if t.get("status") == "error"][-5:]
    error_patterns = []
    for t in recent_errors:
        # Extract keywords from title and description
        words = re.findall(r"\b\w{4,}\b", (t.get("title", "") + " " + t.get("description", "")))
        error_patterns.extend(words)
    
    # 2. ANALYZE ARCHITECTURAL GAPS (Practice Frontier)
    practice_path = Path("conductor/CURRENT_PRACTICE.md")
    frontier_topics = []
    if practice_path.exists():
        content = read_text_fallback(practice_path)
        # Look for the "Next Steps" or "Research Frontier" section
        frontier_match = re.search(r"## 3\. RESEARCH FRONTIER.*?\n(.*?)(?:\n##|$)", content, re.DOTALL | re.IGNORECASE)
        if frontier_match:
            frontier_topics = re.findall(r"- \*\*(.*?)\*\*", frontier_match.group(1))

    # 3. ANALYZE MEMORY DEPTH
    memory_path = Path("agent/MEMORY.md")
    missing_depth = []
    if memory_path.exists():
        # Heuristic: topics mentioned in memory but no artifact exists in agent/skills/auto_generated
        artifact_dir = Path("agent/skills/auto_generated")
        existing_artifacts = [p.stem for p in artifact_dir.glob("*.md")]
        
        # Simple extraction of bracketed topics like [RESEARCH_AUTO] Scraped for 'Topic'
        mentions = re.findall(r"Scraped (?:via .*? )?for '(.*?)'", read_text_fallback(memory_path))
        # Find mentions without artifacts (very basic logic)
        # For now, just use these as candidate fillers
    
    # 4. SYNTHESIZE & PERSONALIZE
    print(f"  [Analyst] Found {len(recent_errors)} recent errors.")
    print(f"  [Analyst] Found {len(frontier_topics)} frontier goals.")
    
    selected = ""
    reason = ""
    
    if frontier_topics:
        raw_topic = frontier_topics[0]
        # Convert "Context Compression" -> "python library for context compression in ai agents"
        selected = f"best python libraries and patterns for {raw_topic.lower()} in autonomous agents"
        reason = "Strategic Frontier Goal (Naturalized)"
    elif error_patterns:
        from collections import Counter
        counts = Counter(error_patterns)
        top_error = counts.most_common(1)[0][0]
        # Convert "Subprocess" -> "how to fix subprocess error python best practices"
        selected = f"how to fix {top_error.lower()} error python best practices"
        reason = f"Urgent Error Fix: {top_error}"
    else:
        # Fallback to a rotating "Discovery Persona"
        personas = [
            "latest autonomous ai agent architecture patterns github",
            "state of the art python tools for ai agents 2026",
            "efficient vector memory libraries for python agents"
        ]
        import random
        selected = random.choice(personas)
        reason = "Exploratory Discovery (Random Persona)"
        
    print(f"\nSELECTED TOPIC: {selected}")
    print(f"REASON: {reason}")
    
    return selected, reason

if __name__ == "__main__":
    identify_next_topic()
