#!/usr/bin/env python3
"""
Test script to verify GitHub Agent internal environment.
Copies the verification script to the container and executes it.
"""
import subprocess
import sys
import os

CONTAINER_NAME = "finopti-github-agent"
# Local path relative to repo root
LOCAL_SCRIPT_PATH = "sub_agents/github_agent_adk/test_llm.py"
CONTAINER_SCRIPT_PATH = "/app/verify_environment.py"

def run_test():
    print(f"Running GitHub Agent Environment Test...")
    
    # 1. Copy script to container
    print(f"Copying {LOCAL_SCRIPT_PATH} to {CONTAINER_NAME}:{CONTAINER_SCRIPT_PATH}...")
    try:
        subprocess.run(
            ["docker", "cp", LOCAL_SCRIPT_PATH, f"{CONTAINER_NAME}:{CONTAINER_SCRIPT_PATH}"],
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"FAILED to copy script: {e}")
        return False

    # 2. Execute script
    print(f"Executing script inside container...")
    try:
        result = subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "python", CONTAINER_SCRIPT_PATH],
            check=False, # We want to handle return code manually
            capture_output=True,
            text=True
        )
        
        print("--- Output from container ---")
        print(result.stdout)
        if result.stderr:
            print("--- Stderr ---")
            print(result.stderr)
        print("-------------------------------")
        
        if result.returncode == 0:
            print("Test PASSED.")
            return True
        else:
            print(f"Test FAILED with exit code {result.returncode}")
            return False
            
    except Exception as e:
        print(f"Exception during execution: {e}")
        return False
    finally:
        # Cleanup
        subprocess.run(["docker", "exec", CONTAINER_NAME, "rm", "-f", CONTAINER_SCRIPT_PATH], check=False)

if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
