import json
import subprocess
import sys

def test_context_tool_dump(tmp_path):
    # Run the tool as a subprocess
    result = subprocess.run(
        [sys.executable, "-m", "autodna.tools.context", "dump"],
        capture_output=True,
        text=True,
        encoding="utf-8"
    )

    assert result.returncode == 0
    
    # Verify it's valid JSON
    data = json.loads(result.stdout)
    
    # Check expected keys
    assert "cwd" in data
    assert "git_status" in data
    assert "recent_commits" in data
    assert "file_tree" in data
    assert "env_vars" in data
    
    # Basic data validation
    assert isinstance(data["file_tree"], dict)
    assert isinstance(data["env_vars"], dict)
