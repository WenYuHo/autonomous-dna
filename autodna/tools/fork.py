import argparse
import subprocess
import sys
import os
import json
from pathlib import Path
from datetime import datetime, timezone

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from autodna.tools.memory import IntelligentMemory

def run_fork(agent_name: str, mission: str, platform: str = "GEMINI"):
    """Forks the context and runs a sub-agent session."""
    print(f"--- 🔱 Forking Context: {agent_name} ---")
    
    # 1. Retrieve Relevant Context ONLY
    print("[1/3] Preparing mission-specific memory...")
    im = IntelligentMemory()
    relevant_facts = im.retrieve_relevant(mission, limit=10)
    
    # Create a temporary fork memory file
    fork_mem_path = Path(f"agent/fork_{agent_name}_memory.md")
    with open(fork_mem_path, "w", encoding="utf-8") as f:
        f.write(f"# FORK MEMORY: {agent_name}\n")
        f.write(f"# Mission: {mission}\n\n")
        for fact in relevant_facts:
            f.write(f"- {fact}\n")
            
    # 2. Spawn Sub-Agent
    print(f"[2/3] Spawning sub-agent on {platform}...")
    # Use agent_runner.py to execute the mission
    cmd = [
        sys.executable, 
        "autodna/core/agent_runner.py", 
        agent_name, 
        f"CONTEXT_FILE: {fork_mem_path}\nMISSION: {mission}"
    ]
    
    # Run and capture output
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    
    # 3. Consolidate Result
    print("[3/3] Consolidating results...")
    if result.returncode == 0:
        # Extract the final "Synthesized Fact" from the sub-agent's output
        # In a real scenario, we'd have a specific marker or tool call.
        # For now, we take the last 10 lines as the summary.
        summary = "\n".join(result.stdout.splitlines()[-10:])
        im.add_fact(f"Fork {agent_name} success: {summary}", source=f"fork_{agent_name}", trust=0.9)
        print("✅ Fork merged successfully.")
    else:
        print(f"❌ Fork failed: {result.stderr}")
        
    # Cleanup
    if fork_mem_path.exists():
        fork_mem_path.unlink()

def main():
    parser = argparse.ArgumentParser(description="Context Forking Tool")
    parser.add_argument("agent_name", help="Name for the sub-agent")
    parser.add_argument("mission", help="Specific task for the sub-agent")
    parser.add_argument("--platform", default="GEMINI", help="Target platform")
    
    args = parser.parse_args()
    run_fork(args.agent_name, args.mission, args.platform)

if __name__ == "__main__":
    main()
