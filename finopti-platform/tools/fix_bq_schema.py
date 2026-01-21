from google.cloud import bigquery
from config import config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_schema():
    client = bigquery.Client(project=config.GCP_PROJECT_ID)
    table_id = f"{config.GCP_PROJECT_ID}.agent_analytics.agent_events_v3"
    
    logger.info(f"Checking table {table_id}...")
    try:
        table = client.get_table(table_id)
        
        # Check content_parts mode
        needs_fix = False
        for field in table.schema:
            if field.name == "content_parts":
                logger.info(f"Field 'content_parts' mode: {field.mode}")
                if field.mode != "REPEATED":
                    needs_fix = True
                break
        
        if needs_fix:
            logger.warning("Schema mismatch detected! Dropping table...")
            client.delete_table(table_id, not_found_ok=True)
            logger.info("Table dropped. It should be recreated by the agent/plugin on next run.")
        else:
            logger.info("Schema looks correct (REPEATED). No action needed.")
            
    except Exception as e:
        logger.error(f"Error accessing table: {e}")

if __name__ == "__main__":
    fix_schema()
