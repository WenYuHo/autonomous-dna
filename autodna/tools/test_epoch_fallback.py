
import subprocess
import sys
from unittest.mock import MagicMock, patch

# Simulate the epoch.py logic
command = [sys.executable, "-c", "print('SIGNAL: FALLBACK_REQUIRED')"]

print("Running simulated epoch command...")
result = subprocess.run(command, capture_output=True, text=True)
output = result.stdout

if "SIGNAL: FALLBACK_REQUIRED" in output:
    print("fallback_detected: 1.0")
else:
    print("fallback_detected: 0.0")
