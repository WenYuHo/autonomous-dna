import subprocess
import sys
from pathlib import Path

def test_critic_tool_runs(tmp_path):
    target_file = tmp_path / "target.py"
    target_file.write_text("print('hello')", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "autodna.tools.critic", str(target_file)],
        capture_output=True,
        text=True,
        encoding="utf-8"
    )

    assert result.returncode == 0
    assert "--- CRITIQUE:" in result.stdout
    assert "[SECURITY]" in result.stdout
    assert "[PERFORMANCE]" in result.stdout
    assert "[STYLE]" in result.stdout
