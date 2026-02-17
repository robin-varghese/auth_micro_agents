import sys
import asyncio
import json
from unittest.mock import MagicMock, patch

# Mock dependencies BEFORE importing tools
sys.modules["context"] = MagicMock()
sys.modules["context"]._report_progress = MagicMock()
# Make _report_progress awaitable
async def mock_report(*args, **kwargs): pass
sys.modules["context"]._report_progress.side_effect = mock_report

sys.modules["config"] = MagicMock()
sys.modules["config"].config.APISIX_URL = "http://mock-apisix"
sys.modules["common.observability"] = MagicMock()

# Add path
sys.path.append("/Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/mats-agents/mats-sre-agent")

from tools import read_logs

async def test_read_logs():
    print("Testing read_logs delegation...")
    
    with patch("requests.post") as mock_post:
        # Mock Response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": "Found 5 error logs related to IAM permission denied."
        }
        mock_post.return_value = mock_response
        
        # Execute
        result = await read_logs("test-project", "severity=ERROR")
        
        # Assertions
        print(f"Result: {result}")
        assert "summary" in result
        assert "Found 5 error logs" in result["summary"]
        
        # Verify Call
        args, kwargs = mock_post.call_args
        assert args[0] == "http://mock-apisix/agent/monitoring/execute"
        assert kwargs["json"]["project_id"] == "test-project"
        assert "severity=ERROR" in kwargs["json"]["prompt"]
        
        print("✅ read_logs Verification Passed")

if __name__ == "__main__":
    asyncio.run(test_read_logs())
