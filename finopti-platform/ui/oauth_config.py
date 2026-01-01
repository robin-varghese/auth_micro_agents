"""
OAuth Credentials Loader - Secret Manager Integration
Loads OAuth credentials from Google Secret Manager
"""

import os
from google.cloud import secretmanager
from typing import Dict, Optional


class OAuthCredentialsLoader:
    """Load OAuth credentials from Google Secret Manager"""
    
    def __init__(self, project_id: Optional[str] = None):
        """
        Initialize the credentials loader.
        
        Args:
            project_id: GCP project ID. If None, uses GOOGLE_CLOUD_PROJECT env var.
        """
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "vector-search-poc")
        self.client = None
        
    def _get_client(self) -> secretmanager.SecretManagerServiceClient:
        """Get or create Secret Manager client"""
        if self.client is None:
            self.client = secretmanager.SecretManagerServiceClient()
        return self.client
    
    def get_secret(self, secret_id: str, version: str = "latest") -> str:
        """
        Get a secret value from Secret Manager.
        
        Args:
            secret_id: The secret ID (e.g., 'google-oauth-client-id')
            version: Secret version (default: 'latest')
            
        Returns:
            The secret value as a string
            
        Raises:
            Exception: If secret cannot be accessed
        """
        client = self._get_client()
        name = f"projects/{self.project_id}/secrets/{secret_id}/versions/{version}"
        
        try:
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")
        except Exception as e:
            raise Exception(f"Failed to access secret '{secret_id}': {str(e)}")
    
    def get_oauth_credentials(self) -> Dict[str, str]:
        """
        Get all OAuth credentials from Secret Manager.
        
        Returns:
            Dictionary with 'client_id', 'client_secret', and 'redirect_uri'
            
        Raises:
            Exception: If any credential cannot be loaded
        """
        try:
            credentials = {
                "client_id": self.get_secret("google-oauth-client-id"),
                "client_secret": self.get_secret("google-oauth-client-secret"),
                "redirect_uri": "http://localhost:8501/_oauth_callback"  # Static for now
            }
            
            # Validate that we got valid values
            if not credentials["client_id"] or not credentials["client_secret"]:
                raise ValueError("OAuth credentials are empty")
            
            return credentials
            
        except Exception as e:
            raise Exception(f"Failed to load OAuth credentials from Secret Manager: {str(e)}")


def load_oauth_config() -> Dict[str, str]:
    """
    Load OAuth configuration from Secret Manager.
    
    Returns:
        Dictionary with OAuth credentials
        
    Raises:
        Exception: If credentials cannot be loaded
    """
    loader = OAuthCredentialsLoader()
    return loader.get_oauth_credentials()


# For testing
if __name__ == "__main__":
    try:
        config = load_oauth_config()
        print("✅ Successfully loaded OAuth credentials from Secret Manager")
        print(f"Client ID: {config['client_id'][:20]}...")
        print(f"Client Secret: {config['client_secret'][:10]}...")
        print(f"Redirect URI: {config['redirect_uri']}")
    except Exception as e:
        print(f"❌ Error: {e}")
