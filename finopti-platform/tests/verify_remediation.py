import sys
import os
import asyncio
import json
from unittest.mock import MagicMock, patch, AsyncMock

# Add agent path
sys.path.append("/Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/mats-agents/mats-remediation-agent")

# Mock dependencies BEFORE importing agent
sys.modules["google.adk.agents"] = MagicMock()
sys.modules["google.adk.apps"] = MagicMock()
sys.modules["google.adk.runners"] = MagicMock()
sys.modules["google.adk.plugins"] = MagicMock()
sys.modules["google.genai"] = MagicMock()
sys.modules["observability"] = MagicMock()

# Context mocks (Async)
mock_context = MagicMock()
mock_context._report_progress = AsyncMock()
sys.modules["context"] = mock_context

sys.modules["common"] = MagicMock()
sys.modules["common.observability"] = MagicMock()

# Mock Tools
with patch("tools.run_puppeteer_test") as mock_pup, \
     patch("tools.apply_gcloud_fix") as mock_fix, \
     patch("tools.check_monitoring") as mock_mon, \
     patch("tools.upload_to_gcs") as mock_upload:

    from agent import extract_remediation_spec, process_remediation

    # Setup Mocks
    mock_pup.return_value = {"status": "FAILURE"} # Initial check fails
    mock_fix.return_value = {"status": "SUCCESS"}
    mock_mon.return_value = {"status": "SUCCESS"}
    mock_upload.return_value = "gs://bucket/remediation_report.md"

    def test_extraction():
        print("Testing JSON Extraction...")
        with open("tests/test_rca.json", "r") as f:
            content = f.read()
            
        spec = extract_remediation_spec(content)
        assert spec["target_url"] == "http://calculator-service:8080"
        assert "gcloud run services" in spec["remediation_command"]
        print("✅ JSON Extraction Passed")

    def test_workflow():
        print("Testing Workflow...")
        # Minimal valid JSON to trigger the workflow
        content = json.dumps({
            "remediation_spec": {
                "target_url": "http://calculator-service:8080",
                "reproduction_scenario": "Check for HTTP 500",
                "remediation_command": "gcloud run services update calculator",
                "validation_query": "rate(errors) < 0.1"
            }
        })

        # Run async function synchronously
        result = process_remediation(content, resolution_plan=None, session_id="test-session")
        
        print(f"Result: {result}")
        assert result["status"] == "SUCCESS"
        assert result["report_url"] == "gs://bucket/remediation_report.md"
        print("✅ Workflow Passed")

    if __name__ == "__main__":
        test_extraction()
        test_workflow()
