import asyncio
import sys
from pathlib import Path

import os
import uuid

# Disable Phoenix for local test
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:4317" # Dummy or ignore
os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = "" # Disable
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["USE_SECRET_MANAGER"] = "FALSE"
os.environ["GOOGLE_CLOUD_PROJECT"] = "vector-search-poc"
os.environ["GCP_PROJECT_ID"] = "vector-search-poc"

# Add agent directory to path
sys.path.append(str(Path(__file__).parent))

from agent import process_request

async def test_iam_agent():
    print("--- Testing IAM Verification Agent ---")
    
    # Mock some context
    user_email = "test-user@example.com"
    project_id = "vector-search-poc"
    session_id = f"test-session-{uuid.uuid4().hex[:8]}"
    
    # Test Prompt
    prompt = f"Verify my permissions for project {project_id}. I need to troubleshoot a crash in the 'auth-service' running on Cloud Run."
    
    print(f"Prompt: {prompt}")
    try:
        response = await process_request(
            prompt, 
            user_email=user_email, 
            session_id=session_id,
            project_id=project_id
        )
        print("\nAgent Response:")
        print("-" * 50)
        print(response)
        print("-" * 50)
        
        if "roles" in response.lower() or "permission" in response.lower():
            print("\n✅ IAM Agent verification SUCCESS (Response contains relevant keywords)")
        else:
            print("\n❌ IAM Agent verification FAILED (Unexpected response)")
            
    except Exception as e:
        print(f"\n❌ Error during verification: {e}")

if __name__ == "__main__":
    asyncio.run(test_iam_agent())
