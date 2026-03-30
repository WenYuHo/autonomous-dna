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
        current_year = datetime.now().year
        # BROADER KEYWORDS: e.g. "context compression python agents 2026 github" 
        # instead of "best python libraries and patterns for..."
        selected = f"{raw_topic.lower()} python agents {current_year} github"
        reason = "Strategic Frontier Goal (Streamlined)"
    elif error_patterns:
        from collections import Counter
        counts = Counter(error_patterns)
        top_error = counts.most_common(1)[0][0]
        current_year = datetime.now().year
        # "fix subprocess error python 2026"
        selected = f"fix {top_error.lower()} error python {current_year} best practices"
        reason = f"Urgent Error Fix: {top_error}"
    else:
        # Fallback to a rotating "Discovery Persona"
        current_year = datetime.now().year
        personas = [
            f"latest autonomous ai agent architecture patterns github {current_year}",
            f"harness engineering ai agents {current_year}",
            f"agentic workflow patterns comparison {current_year} blog",
            f"memory management patterns for large language model agents {current_year}",
            f"state of the art python tools for ai agents {current_year}"
        ]
        import random
        selected = random.choice(personas)
        reason = "Exploratory Discovery (Modern Persona)"
        
    print(f"\nSELECTED TOPIC: {selected}")
    print(f"REASON: {reason}")
    
    return selected, reason

if __name__ == "__main__":
    identify_next_topic()
