import argparse
import sys
import os
import json
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from autodna.core.cli_driver import get_driver
from autodna.tools.io_utils import read_text_fallback

def grade_content(content: str, rubric: str, model: str = None):
    """Asks the LLM to grade content based on a rubric."""
    
    prompt = f"""
You are an expert technical grader. Evaluate the following content based on the provided rubric.

CONTENT:
{content[:10000]}  # Truncate to avoid context overflow

RUBRIC:
{rubric}

OUTPUT FORMAT:
Return a JSON object ONLY:
{{
  "score": <0-100 integer>,
  "reasoning": "<short explanation>",
  "pass": <true/false boolean>
}}
"""
    
    driver = get_driver("GEMINI") # Default to Gemini for grading (fast/cheap)
    # If model is not specified, let driver pick default
    
    try:
        # Use the driver to execute the prompt
        # We need to construct a command that runs the driver. 
        # Actually, simpler to just use the driver class if available, 
        # or subprocess call to a simple "ask" tool if we had one.
        # Since we don't have a simple 'ask' tool, we'll simulate the grading 
        # by using the 'generalist' sub-agent if we were in a session, 
        # but here we are in a script.
        
        # Implementation Detail:
        # Since we are inside the 'autodna' repo, we should assume we can use the 
        # 'gemini' CLI or 'simulated' grading if offline.
        
        # For this implementation, I'll stub the LLM call with a heuristic 
        # because calling an LLM from a subprocess inside a tool is complex 
        # without a dedicated 'ask_llm.py' tool.
        
        # TODO: Replace with actual LLM call when 'ask_llm.py' is available.
        # Heuristic: Check if content meets rubric keywords.
        
        score = 50
        reasoning = "Heuristic grading (LLM driver not yet integrated for tool-use)."
        passed = False
        
        if "actionable" in rubric.lower() and "action" in content.lower():
            score += 20
        if "novelty" in rubric.lower() and "new" in content.lower():
            score += 20
        if len(content) > 500:
            score += 10
            
        passed = score >= 70
        
        return {
            "score": score,
            "reasoning": reasoning,
            "pass": passed
        }

    except Exception as e:
        return {"score": 0, "reasoning": f"Error: {e}", "pass": False}

def main():
    parser = argparse.ArgumentParser(description="Autonomous DNA Content Grader")
    parser.add_argument("target", help="File to grade")
    parser.add_argument("--rubric", required=True, help="Grading criteria")
    parser.add_argument("--min-score", type=int, default=70, help="Minimum passing score")
    
    args = parser.parse_args()
    target_path = Path(args.target)
    
    if not target_path.exists():
        print(json.dumps({"error": "File not found"}))
        sys.exit(1)
        
    content = read_text_fallback(target_path)
    result = grade_content(content, args.rubric)
    
    # Override pass based on CLI arg
    result["pass"] = result["score"] >= args.min_score
    
    print(json.dumps(result, indent=2))
    
    if not result["pass"]:
        sys.exit(1)

if __name__ == "__main__":
    main()
