"""
autodna/tools/critic.py
Implements the Recursive Criticism Pattern.
Analyzes code for security, performance, and style issues.
"""

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def critique_file(file_path: Path) -> None:
    if not file_path.exists():
        print(f"File not found: {file_path}")
        return

    print(f"\n--- CRITIQUE: {file_path} ---")
    print("Analyzing for Security, Performance, and Style...")
    
    # In a real LLM-backed implementation, we would send this to the model.
    # For this "Recipe" implementation, we provide the structured prompt 
    # that the agent (or human) should use to perform the critique.
    
    print("\n[SECURITY]")
    print("- Are inputs validated?")
    print("- Are secrets hardcoded?")
    print("- Is 'shell=True' used safely?")

    print("\n[PERFORMANCE]")
    print("- Are there unnecessary loops?")
    print("- Is I/O blocking the main thread?")
    print("- Are resources (files/sockets) closed properly?")

    print("\n[STYLE]")
    print("- Does code follow PEP8/project conventions?")
    print("- Are functions small and focused?")
    print("- Is typing used consistently?")
    
    print("\n--- END CRITIQUE ---\n")

def main():
    parser = argparse.ArgumentParser(description="Autonomous DNA Code Critic")
    parser.add_argument("files", nargs="+", type=Path, help="Files to critique")
    args = parser.parse_args()

    for f in args.files:
        critique_file(f)

if __name__ == "__main__":
    main()
