
import asyncio
import sys
import os
from unittest.mock import MagicMock

# Add parent directory to path to import agent modules
# Add parent directory to path to import agent modules and common
# we need to go up two levels to reach 'finopti-platform' where 'common' resides? 
# actually 'common' is in 'finopti-platform/common'
# agent.py is in 'finopti-platform/mats-agents/mats-remediation-agent'
# tools.py imports 'common.observability'
# so we need to add 'finopti-platform' to sys.path

current_dir = os.path.dirname(os.path.abspath(__file__))
# current_dir = .../mats-remediation-agent
# parent_dir = .../mats-agents
# grand_parent_dir = .../finopti-platform

current_dir = os.path.dirname(os.path.abspath(__file__))
# current_dir: .../finopti-platform/mats-agents/mats-remediation-agent
# parent_dir: .../finopti-platform/mats-agents
# project_root: .../finopti-platform (where 'common' lives)

project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir))) 
# Wait, let's just hardcode to be safe or verify with one list_dir
# All code seems to be under /Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform

project_root = "/Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform"
sys.path.append(project_root)
sys.path.append(current_dir)

# Mock the dependencies that are causing import errors
sys.modules["common"] = MagicMock()
sys.modules["common.observability"] = MagicMock()
sys.modules["tools"] = MagicMock()

from agent import extract_field

def test_rca_parsing():
    rca_content = """
    [Incident ID] - Autonomous Root Cause Analysis
    ...
    **8. Automation & Remediation Spec (Machine Readable)**
    *Directive: Provide executable commands and queries for the Remediation Agent.*

    TARGET_URL: http://example.com/api/v1
    REPRODUCTION_SCENARIO: Check for 500 error on login
    REMEDIATION_COMMAND: gcloud run services update my-service --memory=2Gi
    VALIDATION_QUERY: sum(rate(http_requests_total{status="500"}[5m]))
    VALIDATION_THRESHOLD: < 1
    """

    print("Testing RCA Parsing...")
    
    url = extract_field(rca_content, "TARGET_URL")
    print(f"URL: {url} [{'OK' if url == 'http://example.com/api/v1' else 'FAIL'}]")
    
    cmd = extract_field(rca_content, "REMEDIATION_COMMAND")
    print(f"Command: {cmd} [{'OK' if cmd == 'gcloud run services update my-service --memory=2Gi' else 'FAIL'}]")
    
    query = extract_field(rca_content, "VALIDATION_QUERY")
    print(f"Query: {query} [{'OK' if query == 'sum(rate(http_requests_total{status=\"500\"}[5m]))' else 'FAIL'}]")

if __name__ == "__main__":
    test_rca_parsing()
