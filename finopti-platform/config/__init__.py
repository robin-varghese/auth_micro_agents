"""
Centralized configuration for FinOptiAgents Platform

Loads configuration from Google Secret Manager (production) with fallback to .env (local dev).
All modules should import configuration from this file.
"""

import os
import logging
from pathlib import Path
from typing import Optional

import google.auth
from google.cloud import secretmanager
from google.cloud import resourcemanager_v3
from google.api_core import exceptions
from dotenv import load_dotenv

# =======================================================================================
# LOGGING CONFIGURATION
# =======================================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)

# =======================================================================================
# HELPER FUNCTIONS
# =======================================================================================

def _get_secret_value(project_id: str, secret_id: str, client: secretmanager.SecretManagerServiceClient) -> Optional[str]:
    """
    Helper function to fetch a single secret from Secret Manager.
    
    Args:
        project_id: GCP project ID
        secret_id: Secret identifier (will use lowercase with hyphens)
        client: Secret Manager client
        
    Returns:
        Secret value or None if not found
    """
    if not project_id:
        return None
    
    # Convert secret_id to Secret Manager format (lowercase, hyphens)
    # e.g., "GOOGLE_API_KEY" -> "google-api-key"
    secret_name = secret_id.lower().replace('_', '-')
    name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    
    try:
        response = client.access_secret_version(request={"name": name})
        value = response.payload.data.decode("UTF-8")
        logger.info(f"Successfully fetched secret: '{secret_name}'")
        return value
    except exceptions.NotFound:
        logger.warning(f"Secret '{secret_name}' not found in project '{project_id}'.")
        return None
    except Exception as e:
        logger.warning(f"Could not fetch secret '{secret_name}': {e}")
        return None


def _resolve_project_id_from_number(project_number: str) -> Optional[str]:
    """
    Given a project number, resolves it to the project ID string.
    
    Args:
        project_number: GCP project number
        
    Returns:
        Project ID string or None if resolution fails
    """
    try:
        logger.info(f"Attempting to resolve project ID from project number: {project_number}...")
        client = resourcemanager_v3.ProjectsClient()
        project_path = f"projects/{project_number}"
        project = client.get_project(name=project_path)
        project_id = project.project_id
        logger.info(f"Successfully resolved project number '{project_number}' to project ID: '{project_id}'")
        return project_id
    except Exception as e:
        logger.error(f"Failed to resolve project ID from number '{project_number}': {e}", exc_info=True)
        return None


# =======================================================================================
# LOAD CONFIGURATION
# =======================================================================================

logger.info("--- Loading FinOptiAgents configuration ---")

# Try to load from .env file first (for local development)
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
    logger.info(f"Loaded environment variables from {env_path}")
    USE_SECRET_MANAGER = os.getenv('USE_SECRET_MANAGER', 'false').lower() == 'true'
else:
    # In production (no .env file), always use Secret Manager
    USE_SECRET_MANAGER = True
    logger.info("No .env file found, using Secret Manager")

# Initialize Secret Manager client
_secret_client = secretmanager.SecretManagerServiceClient()

# =======================================================================================
# DETERMINE PROJECT ID
# =======================================================================================

# Try multiple sources for project ID
_initial_project_identifier = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT_ID")

if not _initial_project_identifier:
    try:
        _, _initial_project_identifier = google.auth.default()
        logger.info(f"Discovered project from default credentials: {_initial_project_identifier}")
    except google.auth.exceptions.DefaultCredentialsError:
        _initial_project_identifier = None
        logger.warning("Could not discover project from default credentials")

# Try to get project ID from Secret Manager
if USE_SECRET_MANAGER and _initial_project_identifier:
    _project_identifier_from_secret = _get_secret_value(
        _initial_project_identifier, 
        "GOOGLE_PROJECT_ID",  # Will be converted to "google-project-id"
        _secret_client
    )
    _final_project_identifier = _project_identifier_from_secret or _initial_project_identifier
else:
    _final_project_identifier = _initial_project_identifier

# Handle project number → project ID resolution
if _final_project_identifier and _final_project_identifier.isdigit():
    logger.info(f"Project identifier '{_final_project_identifier}' appears to be a project number.")
    GOOGLE_PROJECT_ID = _resolve_project_id_from_number(_final_project_identifier)
else:
    GOOGLE_PROJECT_ID = _final_project_identifier

if not GOOGLE_PROJECT_ID:
    raise ValueError(
        "FATAL: Could not determine Google Cloud Project ID. "
        "Please set GOOGLE_CLOUD_PROJECT, GCP_PROJECT_ID env var, or 'google-project-id' secret."
    )

logger.info(f"Using Project ID: {GOOGLE_PROJECT_ID}")

# Backwards compatibility
PROJECT_ID = GOOGLE_PROJECT_ID
GCP_PROJECT_ID = GOOGLE_PROJECT_ID


# =======================================================================================
# HELPER TO FETCH CONFIG VALUES
# =======================================================================================

def _fetch_config(secret_id: str, env_var: Optional[str] = None, default: Optional[str] = None) -> Optional[str]:
    """
    Fetch configuration value from Secret Manager or environment variable.
    
    Priority:
    1. Secret Manager (if USE_SECRET_MANAGER is True)
    2. Environment variable
    3. Default value
    
    Args:
        secret_id: Secret identifier (e.g., "GOOGLE_API_KEY")
        env_var: Environment variable name (defaults to secret_id)
        default: Default value if not found
        
    Returns:
        Configuration value or None
    """
    env_var = env_var or secret_id
    
    # Priority 1: Environment variable (allows override)
    value = os.getenv(env_var)
    if value:
        logger.info(f"Using environment variable for {env_var}")
        return value

    # Priority 2: Secret Manager (in production)
    if USE_SECRET_MANAGER:
        value = _get_secret_value(GOOGLE_PROJECT_ID, secret_id, _secret_client)
        if value:
            return value
    
    # Priority 3: Default
    if default:
        logger.info(f"Using default value for {secret_id}")
        return default
    
    logger.warning(f"No value found for {secret_id}")
    return None


# =======================================================================================
# LOAD ALL CONFIGURATION VALUES
# =======================================================================================

# Core Google Cloud
GOOGLE_API_KEY = _fetch_config("GOOGLE_API_KEY")
FINOPTIAGENTS_LLM = _fetch_config("FINOPTIAGENTS_LLM", default="gemini-3-flash-preview")
GOOGLE_GENAI_USE_VERTEXAI = _fetch_config("GOOGLE_GENAI_USE_VERTEXAI", default="FALSE")
GOOGLE_ZONE = _fetch_config("GOOGLE_ZONE", default="us-central1-a")

# Storage
STAGING_BUCKET_URI = _fetch_config("STAGING_BUCKET_URI")
PROD_BUCKET_URI = _fetch_config("PROD_BUCKET_URI")
PACKAGE_URI = _fetch_config("PACKAGE_URI")

# Database
GOOGLE_DB_URI = _fetch_config("GOOGLE_DB_URI")

# BigQuery
BIGQUERY_DATASET_ID = _fetch_config("BIGQUERY_DATASET_ID", default="finoptiagents")
BIGQUERY_TABLE_ID = _fetch_config("BIGQUERY_TABLE_ID", default="vm_deletion_log")
BIGQUERYAGENTANALYTICSPLUGIN_TABLE_ID = _fetch_config("BIGQUERYAGENTANALYTICSPLUGIN_TABLE_ID", default="agent_analytics_log")

# RAG Configuration
RAG_Engine_LOCATION = _fetch_config("RAG_Engine_LOCATION", default="us-east4")
RAG_EARB_DESIGNDOCS = _fetch_config("RAG_EARB_DESIGNDOCS")
RAG_GOOGLE_GENAI_USE_VERTEXAI = _fetch_config("RAG_GOOGLE_GENAI_USE_VERTEXAI", default="True")

# MCP Configuration
MCP_TOOLBOX_URL = _fetch_config("MCP_TOOLBOX_URL", default="http://127.0.0.1:5001")
TOOLSET_NAME_FOR_LOGGING = _fetch_config("TOOLSET_NAME_FOR_LOGGING", default="my_googleaiagent_toolset")
LOGGING_TOOL_NAME = _fetch_config("LOGGING_TOOL_NAME", default="insert-user-action-and-result")

# Service URLs (for FinOptiAgents platform)
OPA_URL = _fetch_config("OPA_URL", default="http://opa:8181")
APISIX_URL = _fetch_config("APISIX_URL", default="http://apisix:9080")
GCLOUD_MCP_DOCKER_IMAGE = _fetch_config("GCLOUD_MCP_DOCKER_IMAGE", default="finopti-gcloud-mcp")
GCLOUD_MOUNT_PATH = _fetch_config("GCLOUD_MOUNT_PATH", default="~/.config/gcloud:/root/.config/gcloud")
MONITORING_MCP_URL = _fetch_config("MONITORING_MCP_URL", default="http://monitoring_mcp:6002")
MONITORING_MCP_DOCKER_IMAGE = _fetch_config("MONITORING_MCP_DOCKER_IMAGE", default="finopti-monitoring-mcp")

# New MCP Servers
GITHUB_PERSONAL_ACCESS_TOKEN = _fetch_config("GITHUB_PERSONAL_ACCESS_TOKEN")
GITHUB_MCP_DOCKER_IMAGE = _fetch_config("GITHUB_MCP_DOCKER_IMAGE", default="finopti-github-mcp")
STORAGE_MCP_DOCKER_IMAGE = _fetch_config("STORAGE_MCP_DOCKER_IMAGE", default="finopti-storage-mcp")
# DB Toolbox uses a direct image reference in docker-compose, but we can config the URL if needed
DB_MCP_TOOLBOX_URL = _fetch_config("DB_MCP_TOOLBOX_URL", default=f"{APISIX_URL}/mcp/db")

# Observability
LOG_LEVEL = _fetch_config("LOG_LEVEL", default="INFO")
ENABLE_STRUCTURED_LOGGING = _fetch_config("ENABLE_STRUCTURED_LOGGING", default="true").lower() == "true"

# Development
DEV_MODE = _fetch_config("DEV_MODE", default="false").lower() == "true"



# =======================================================================================
# VALIDATION
# =======================================================================================

class Config:
    """Configuration class for easy access to all settings"""
    
    # All configuration as class attributes
    GOOGLE_PROJECT_ID = GOOGLE_PROJECT_ID
    PROJECT_ID = PROJECT_ID
    GCP_PROJECT_ID = GCP_PROJECT_ID
    
    GOOGLE_API_KEY = GOOGLE_API_KEY
    FINOPTIAGENTS_LLM = FINOPTIAGENTS_LLM
    GOOGLE_GENAI_USE_VERTEXAI = GOOGLE_GENAI_USE_VERTEXAI
    GOOGLE_ZONE = GOOGLE_ZONE
    
    STAGING_BUCKET_URI = STAGING_BUCKET_URI
    PROD_BUCKET_URI = PROD_BUCKET_URI
    PACKAGE_URI = PACKAGE_URI
    GOOGLE_DB_URI = GOOGLE_DB_URI
    
    BIGQUERY_DATASET_ID = BIGQUERY_DATASET_ID
    BIGQUERY_TABLE_ID = BIGQUERY_TABLE_ID
    BIGQUERYAGENTANALYTICSPLUGIN_TABLE_ID = BIGQUERYAGENTANALYTICSPLUGIN_TABLE_ID
    
    RAG_Engine_LOCATION = RAG_Engine_LOCATION
    RAG_EARB_DESIGNDOCS = RAG_EARB_DESIGNDOCS
    RAG_GOOGLE_GENAI_USE_VERTEXAI = RAG_GOOGLE_GENAI_USE_VERTEXAI
    
    MCP_TOOLBOX_URL = MCP_TOOLBOX_URL
    TOOLSET_NAME_FOR_LOGGING = TOOLSET_NAME_FOR_LOGGING
    LOGGING_TOOL_NAME = LOGGING_TOOL_NAME
    
    OPA_URL = OPA_URL
    APISIX_URL = APISIX_URL
    GCLOUD_MCP_DOCKER_IMAGE = GCLOUD_MCP_DOCKER_IMAGE
    GCLOUD_MOUNT_PATH = GCLOUD_MOUNT_PATH
    MONITORING_MCP_URL = MONITORING_MCP_URL
    MONITORING_MCP_DOCKER_IMAGE = MONITORING_MCP_DOCKER_IMAGE
    
    GITHUB_PERSONAL_ACCESS_TOKEN = GITHUB_PERSONAL_ACCESS_TOKEN
    GITHUB_MCP_DOCKER_IMAGE = GITHUB_MCP_DOCKER_IMAGE
    STORAGE_MCP_DOCKER_IMAGE = STORAGE_MCP_DOCKER_IMAGE
    DB_MCP_TOOLBOX_URL = DB_MCP_TOOLBOX_URL
    
    LOG_LEVEL = LOG_LEVEL
    ENABLE_STRUCTURED_LOGGING = ENABLE_STRUCTURED_LOGGING
    DEV_MODE = DEV_MODE
    

    
    @classmethod
    def validate(cls) -> bool:
        """Validate that required configuration is present"""
        required = ['GOOGLE_API_KEY', 'GOOGLE_PROJECT_ID']
        missing = [key for key in required if not getattr(cls, key)]
        
        if missing:
            logger.error(f"Missing required configuration: {', '.join(missing)}")
            return False
        return True
    
    @classmethod
    def to_dict(cls) -> dict:
        """Export all configuration as dictionary"""
        return {
            key: getattr(cls, key)
            for key in dir(cls)
            if not key.startswith('_') and not callable(getattr(cls, key)) and key.isupper()
        }


# Create instance
config = Config()

# Validate
if not config.validate():
    logger.warning("Configuration validation failed - some features may not work")
else:
    logger.info("Configuration loaded and validated successfully")

logger.info(f"Configuration mode: {'Secret Manager' if USE_SECRET_MANAGER else '.env file'}")
