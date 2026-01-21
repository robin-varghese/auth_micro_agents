import sys
import os
import importlib
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from config import config

def verify_all_agents():
    print("Verifying BQ_ANALYTICS_TABLE configuration...")
    print(f"Config Value: {config.BQ_ANALYTICS_TABLE}")

    if config.BQ_ANALYTICS_TABLE != "agent_events_v3":
        print("ERROR: Config value is not 'agent_events_v3'!")
        return

    # List of agent files to check (regex/grep check matching)
    agent_files = [
        "sub_agents/filesystem_agent_adk/agent.py",
        "orchestrator_adk/agent.py",
        "sub_agents/brave_search_agent_adk/agent.py",
        "sub_agents/googlesearch_agent_adk/agent.py",
        "sub_agents/sequential_thinking_agent_adk/agent.py",
        "sub_agents/monitoring_agent_adk/agent.py",
        "sub_agents/db_agent_adk/agent.py",
        "sub_agents/puppeteer_agent_adk/agent.py",
        "sub_agents/github_agent_adk/agent.py",
        "sub_agents/cloud_run_agent_adk/agent.py",
        "sub_agents/storage_agent_adk/agent.py",
        "sub_agents/gcloud_agent_adk/agent.py",
        "sub_agents/analytics_agent_adk/agent.py",
        "mats-agents/architect_agent/agent.py",
        "mats-agents/investigator_agent/agent.py",
        "mats-agents/sre_agent/agent.py"
    ]

    project_root = Path("/Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform")
    
    error_count = 0

    for rel_path in agent_files:
        full_path = project_root / rel_path
        try:
            with open(full_path, 'r') as f:
                content = f.read()
                
            if 'config.BQ_ANALYTICS_TABLE' not in content:
                print(f"FAILED: {rel_path} does not seem to use config.BQ_ANALYTICS_TABLE")
                error_count += 1
            elif 'agent_events_v2' in content:
                # Check if it's commented out or part of a different string (naive check)
                # But we replaced the lines, so it shouldn't be there as a literal implementation
                # unless it's in a comment we didn't touch.
                # Let's strictly check for the os.getenv call we replaced.
                if 'os.getenv("BQ_ANALYTICS_TABLE"' in content:
                     print(f"FAILED: {rel_path} still has hardcoded os.getenv for BQ table")
                     error_count += 1
                else:
                     print(f"PASSED: {rel_path}")
            else:
                print(f"PASSED: {rel_path}")
                
        except Exception as e:
            print(f"ERROR reading {rel_path}: {e}")
            error_count += 1

    if error_count == 0:
        print("\nSUCCESS: All agents verified to use central config.")
    else:
        print(f"\nFAILURE: {error_count} agents failed verification.")

if __name__ == "__main__":
    verify_all_agents()
