
import logging
import google.auth
from google.auth.transport.requests import Request
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mats-permissions")

def check_gcp_credentials():
    """
    Verifies that the container has access to valid GCP credentials.
    Returns: (bool, message, project_id)
    """
    try:
        credentials, project_id = google.auth.default()
        # Refresh if expired
        if not credentials.valid:
            request = Request()
            credentials.refresh(request)
            
        # Verify with API call (List Projects)
        # Using v1 API which is standard
        resp = requests.get(
            "https://cloudresourcemanager.googleapis.com/v1/projects",
            params={"pageSize": 1},
            headers={"Authorization": f"Bearer {credentials.token}"}
        )
        
        if resp.status_code == 401:
             return False, "Invalid Credentials (401). Run gcloud auth application-default login.", None
             
        # Any other code (200, 403) means credentials were accepted (parsed) even if permisson denied.
        return True, "Credentials valid.", project_id

    except google.auth.exceptions.DefaultCredentialsError:
        return False, "No Google Cloud credentials found. Please run 'gcloud auth application-default login' on the host machine.", None
    except Exception as e:
        logger.error(f"Credential check failed: {e}")
        return False, f"Credential verification failed: {str(e)}", None
