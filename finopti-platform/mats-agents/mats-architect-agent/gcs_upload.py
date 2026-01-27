"""
MATS Architect Agent - GCS Upload Integration

Add GCS upload capability for RCA documents.
"""
import os
from google.cloud import storage
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

# GCS Configuration
GCS_BUCKET = os.getenv("MATS_RCA_BUCKET", "mats-rca-reports")
GCS_PROJECT = os.getenv("GCP_PROJECT_ID")


def upload_rca_to_gcs(rca_content: str, session_id: str) -> str:
    """
    Upload RCA markdown to GCS and return signed URL.
    
    Args:
        rca_content: Markdown content of RCA
        session_id: Investigation session ID
        
    Returns:
        Signed URL (valid for 7 days)
    """
    try:
        # Initialize GCS client
        storage_client = storage.Client(project=GCS_PROJECT)
        bucket = storage_client.bucket(GCS_BUCKET)
        
        # Create blob with session ID in name
        blob_name = f"rca/{session_id}/rca_report.md"
        blob = bucket.blob(blob_name)
        
        # Upload content
        blob.upload_from_string(rca_content, content_type="text/markdown")
        
        logger.info(f"Uploaded RCA to gs://{GCS_BUCKET}/{blob_name}")
        
        # Generate signed URL (7 days)
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(days=7),
            method="GET"
        )
        
        return url
        
    except Exception as e:
        logger.error(f"GCS upload failed: {e}")
        return f"https://storage.cloud.google.com/{GCS_BUCKET}/rca/{session_id}/rca_report.md"


# Update architect agent.py to use this:
# After generating RCA content:
# rca_url = upload_rca_to_gcs(rca_content, session_id)
# return {"status": "SUCCESS", "rca_url": rca_url, "rca_content": rca_content, ...}
