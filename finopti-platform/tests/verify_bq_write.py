import os
import sys
import logging
from config import config
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
from google.cloud import bigquery
import time
import uuid

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_bq_write():
    logger.info("--- Starting Direct BigQuery Write Verification ---")
    
    # 1. Verify Configuration
    project_id = config.GCP_PROJECT_ID
    dataset_id = os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics")
    table_id = config.BQ_ANALYTICS_TABLE # This should be 'agent_events_v3'
    
    logger.info(f"Project ID: {project_id}")
    logger.info(f"Dataset ID: {dataset_id}")
    logger.info(f"Table ID:   {table_id}")
    
    if not project_id or not table_id:
        logger.error("❌ Missing required configuration (Project ID or Table ID).")
        return False

    # 2. Check Dataset Existence
    client = bigquery.Client(project=project_id)
    dataset_ref = f"{project_id}.{dataset_id}"
    try:
        client.get_dataset(dataset_ref)
        logger.info(f"✅ Dataset '{dataset_ref}' exists.")
    except Exception as e:
        logger.error(f"❌ Dataset '{dataset_ref}' check failed: {e}")
        return False

    # 3. Check Table Schema
    logger.info(f"Checking schema for {dataset_ref}.{table_id}...")
    try:
        table_ref = f"{project_id}.{dataset_id}.{table_id}"
        table = client.get_table(table_ref)
        schema_fields = [f.name for f in table.schema]
        logger.info(f"Existing Schema Fields: {schema_fields}")
    except Exception as e:
        logger.error(f"❌ Table schema check failed: {e}")
        return False

    # 4. Instantiate Plugin (this keeps reference to configuration)
    logger.info("Instantiating BigQueryAgentAnalyticsPlugin...")
    try:
        bq_plugin = BigQueryAgentAnalyticsPlugin(
            project_id=project_id,
            dataset_id=dataset_id,
            table_id=table_id,
            config=BigQueryLoggerConfig(enabled=True)
        )
        logger.info("✅ Plugin instantiated successfully.")
    except Exception as e:
        logger.error(f"❌ Plugin instantiation failed: {e}")
        return False
        
    # 4. Attempt to Write a Test Row directly via BigQuery Client (simulating Plugin internals)
    # Note: access internal client if possible or just use our own client to verify permissions
    
    table_ref = f"{project_id}.{dataset_id}.{table_id}"
    test_row = {
        "timestamp": time.time(),
        "event_type": "TEST_VERIFICATION",
        "agent": "test_verification_script",
        "session_id": "test_session",
        "user_id": "test_user",
        "content": "Verification script test write",
        "status": "success",
        # "metadata": '{"source": "verify_bq_write.py"}' # REMOVED: Not in schema
        # "event_id": ... # REMOVED
    }
    
    logger.info(f"Attempting to insert test row into {table_ref}...")
    try:
        errors = client.insert_rows_json(table_ref, [test_row])
        if errors:
            logger.error(f"❌ Insert failed with errors: {errors}")
            return False
        else:
            logger.info("✅ Insert successful!")
            return True
    except Exception as e:
        logger.error(f"❌ Insert raised exception: {e}")
        return False

if __name__ == "__main__":
    if verify_bq_write():
        sys.exit(0)
    else:
        sys.exit(1)
