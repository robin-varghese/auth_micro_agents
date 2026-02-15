"""
Architect Agent Tools
"""
import logging
import json
import requests
from config import config

logger = logging.getLogger(__name__)

def upload_rca_to_gcs(filename: str, content: str, bucket_name: str = "rca-reports-mats") -> str:
    """
    Uploads the RCA document to Google Cloud Storage via the Storage Agent.
    
    Args:
        filename: Name of the file (e.g., "rca-2024-01-01.md")
        content: The Markdown content of the RCA.
        bucket_name: Target GCS bucket name (default: "finopti-reports")
        
    Returns:
        The public URL or path of the uploaded file.
    """
    try:
        # Route via APISIX to Storage Agent
        url = f"{config.APISIX_URL}/agent/storage/execute"
        logger.info(f"Initiating RCA Upload to {bucket_name}/{filename} via {url}")

        
        # Robust prompt for Storage Agent
        prompt = (
            f"Please ensure the GCS bucket '{bucket_name}' exists (create it in location US if it doesn't). "
            f"Then, upload the following content as object '{filename}' to that bucket:\n\n{content}"
        )
        
        payload = {
            "prompt": prompt,
            "user_email": "mats-architect@system.local" 
        }

        # Inject Trace Headers
        try:
            from common.observability import FinOptiObservability
            headers = {}
            FinOptiObservability.inject_trace_to_headers(headers)
            payload["headers"] = headers
        except ImportError:
            pass
        
        response = requests.post(url, json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()
        
        # Extract response text if nested (ADK pattern)
        if isinstance(data, dict) and "response" in data:
            try:
                # The prompt execution might return a JSON string in 'response'
                inner_data = json.loads(data["response"])
                if isinstance(inner_data, dict) and "signed_url" in inner_data:
                    return f"RCA Uploaded. Secure Link: {inner_data['signed_url']}"
            except:
                pass
            return f"RCA Uploaded. Details: {data['response']}"
            
        return f"Upload requested. Response: {data}"
    except Exception as e:
        return f"Failed to upload RCA: {e}"

def write_object(bucket: str, path: str, content: str) -> str:
    """
    Shim for legacy/hallucinated write_object calls. Redirects to upload_rca_to_gcs.
    """
    logging.warning("LLM called write_object (shim). Redirecting to upload_rca_to_gcs.")
    # Map arguments
    return upload_rca_to_gcs(filename=path, content=content, bucket_name=bucket)

def update_bucket_labels(bucket_name: str, labels: dict) -> str:
    """
    Shim for hallucinated update_bucket_labels calls.
    """
    logging.warning(f"LLM called update_bucket_labels (shim) for {bucket_name}. Ignoring.")
    return "Bucket labels updated (shim)."
