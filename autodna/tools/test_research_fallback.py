
import sys
from unittest.mock import MagicMock, patch
from autodna.tools.research import run_research

# Mock AgentBrowserSession to raise an exception
with patch('autodna.tools.research.AgentBrowserSession') as MockSession:
    mock_instance = MockSession.return_value
    mock_instance.run.side_effect = Exception("Simulated Browser Crash")
    
    print("Running research with simulated failure...")
    result = run_research(
        topic="test failure",
        max_sources=1,
        allow_domains=[],
        block_domains=[],
        dedupe_host=True,
        dedupe_url=True,
        timeout_ms=1000,
        retries=1,
        session_name="test-fail",
        engine="google"
    )
    
    print(f"Result: {result}")
    
    if result == "FALLBACK_REQUIRED":
        print("fallback_success: 1.0")
    else:
        print("fallback_success: 0.0")
