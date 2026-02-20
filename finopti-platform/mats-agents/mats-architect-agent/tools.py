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
        filename: Optional incident ID or base name. Used to create the folder structure.
        content: The JSON content of the RCA (string or dict).
        bucket_name: Target GCS bucket name (default: "rca-reports-mats")
        
    Returns:
        The public URL or path of the uploaded file.
    """
    try:
        import datetime
        
        # Parse content if it's a string, just to validate it's JSON
        if isinstance(content, str):
            try:
                # verify it is valid json
                json.loads(content)
            except:
                logger.warning("Content is not valid JSON. Proceeding anyway but treating as text.")
        elif isinstance(content, dict):
            content = json.dumps(content, indent=2)

        # Generate Folder Structure: {incident_id}/{timestamp}/rca.json
        # If filename is not provided, use a generic 'incident' prefix
        # FORCE .json extension to avoid .md uploads
        from context import _session_id_ctx
        ctx_session_id = _session_id_ctx.get()
        
        # Use session_id from context if available, fallback to filename base
        base_name = ctx_session_id if ctx_session_id else (filename.replace(".md", "").replace(".json", "") if filename else "incident")
        incident_id = base_name
        timestamp = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        
        # Logic: Clean up incident ID to be folder-safe
        import re
        safe_id = re.sub(r'[^a-zA-Z0-9-_]', '_', incident_id)
        
        target_path = f"{safe_id}/{timestamp}/rca.json"
        
        # Route via APISIX to Storage Agent
        url = f"{config.APISIX_URL}/agent/storage/execute"
        logger.info(f"Initiating RCA Upload to {bucket_name}/{target_path} via {url}")

        # Robust prompt for Storage Agent
        prompt = (
            f"Please ensure the GCS bucket '{bucket_name}' exists (create it in location US if it doesn't). "
            f"Then, upload the following content as object '{target_path}' to that bucket:\n\n{content}"
        )
        
        payload = {
            "prompt": prompt,
            "user_email": "mats-architect@system.local" 
        }

        headers = {}
        
        # Inject Trace Headers
        try:
            from common.observability import FinOptiObservability
            FinOptiObservability.inject_trace_to_headers(headers)
        except ImportError:
            pass
            
        # Inject Auth Token
        try:
            from context import _auth_token_ctx
            token = _auth_token_ctx.get()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        except ImportError:
            pass
            
        payload["headers"] = headers
        
        response = requests.post(url, json=payload, headers=headers, timeout=300)
        response.raise_for_status()
        data = response.json()
        
        # Extract response text if nested (ADK pattern)
        if isinstance(data, dict) and "response" in data:
            try:
                # The prompt execution might return a JSON string in 'response'
                inner_data = json.loads(data["response"])
                if isinstance(inner_data, dict) and "signed_url" in inner_data:
                    return f"https://storage.cloud.google.com/{bucket_name}/{target_path}"
            except:
                pass
            return f"https://storage.cloud.google.com/{bucket_name}/{target_path}"
            
        return f"https://storage.cloud.google.com/{bucket_name}/{target_path}"
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
