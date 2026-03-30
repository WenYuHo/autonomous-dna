import json
import re
from pathlib import Path

class AssertionEvaluator:
    """Evaluates a set of assertions against an artifact or stdout."""
    
    @staticmethod
    def evaluate(content: str, assertions: list[str]) -> dict:
        results = []
        passed_count = 0
        
        for assertion in assertions:
            passed = False
            # 1. Regex Match: "contains: pattern"
            if assertion.startswith("contains:"):
                pattern = assertion.split(":", 1)[1].strip()
                passed = bool(re.search(pattern, content, re.IGNORECASE))
            
            # 2. Exclude Match: "exclude: pattern"
            elif assertion.startswith("exclude:"):
                pattern = assertion.split(":", 1)[1].strip()
                passed = not bool(re.search(pattern, content, re.IGNORECASE))
            
            # 3. Minimum Length: "min_len: 100"
            elif assertion.startswith("min_len:"):
                length = int(assertion.split(":", 1)[1].strip())
                passed = len(content) >= length
                
            # 4. JSON Validation: "is_json"
            elif assertion == "is_json":
                try:
                    json.loads(content)
                    passed = True
                except:
                    passed = False
            
            results.append({"assertion": assertion, "passed": passed})
            if passed: passed_count += 1
            
        score = (passed_count / len(assertions)) * 100 if assertions else 100
        return {
            "score": round(score, 2),
            "passed_count": passed_count,
            "total_count": len(assertions),
            "results": results
        }

if __name__ == "__main__":
    # Quick test
    evaluator = AssertionEvaluator()
    sample = "Research Report: Agent-Browser is great. Source: https://github.com/vercel-labs/agent-browser"
    test_assertions = ["contains: agent-browser", "contains: github.com", "min_len: 50"]
    print(json.dumps(evaluator.evaluate(sample, test_assertions), indent=2))
