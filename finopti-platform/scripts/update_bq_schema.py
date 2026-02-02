from google.cloud import bigquery
from google.cloud.bigquery import SchemaField
import os
import sys

# Ensure we can import config
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from config import config
except ImportError:
    print("Could not import config. Using defaults.")
    class Config:
        GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "vector-search-poc")
        BIGQUERY_DATASET_ID = os.environ.get("BIGQUERY_DATASET_ID", "finoptiagents")
        BIGQUERYAGENTANALYTICSPLUGIN_TABLE_ID = os.environ.get("BIGQUERYAGENTANALYTICSPLUGIN_TABLE_ID", "agent_analytics_log")
    config = Config()

PROJECT_ID = config.GCP_PROJECT_ID
DATASET_ID = config.BIGQUERY_DATASET_ID
TABLE_ID = config.BIGQUERYAGENTANALYTICSPLUGIN_TABLE_ID

def update_schema():
    client = bigquery.Client(project=PROJECT_ID)
    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"
    
    print(f"Fetching table: {table_ref}")
    try:
        table = client.get_table(table_ref)
    except Exception as e:
        print(f"Error getting table: {e}")
        return

    original_schema = table.schema
    new_schema = list(original_schema)
    
    # Define new fields to check/add
    # Based on error logs:
    # Extra: trace_id, parent_span_id, content_parts, latency_ms, attributes, span_id, status
    
    new_fields = [
        SchemaField("trace_id", "STRING", mode="NULLABLE"),
        SchemaField("span_id", "STRING", mode="NULLABLE"),
        SchemaField("parent_span_id", "STRING", mode="NULLABLE"),
        SchemaField("status", "STRING", mode="NULLABLE"),
        SchemaField("attributes", "STRING", mode="NULLABLE"), # Log shows JSON string
        SchemaField("latency_ms", "RECORD", mode="NULLABLE", fields=[
            SchemaField("total_ms", "INTEGER", mode="NULLABLE"),
            SchemaField("time_to_first_token_ms", "INTEGER", mode="NULLABLE"),
        ]),
        SchemaField("content_parts", "RECORD", mode="REPEATED", fields=[
            SchemaField("part_index", "INTEGER", mode="NULLABLE"),
            SchemaField("mime_type", "STRING", mode="NULLABLE"),
            SchemaField("uri", "STRING", mode="NULLABLE"),
            SchemaField("text", "STRING", mode="NULLABLE"),
            SchemaField("part_attributes", "STRING", mode="NULLABLE"),
            SchemaField("storage_mode", "STRING", mode="NULLABLE"),
            SchemaField("object_ref", "STRING", mode="NULLABLE"),
        ]),
    ]
    
    existing_names = {f.name for f in original_schema}
    
    added_count = 0
    for field in new_fields:
        if field.name not in existing_names:
            new_schema.append(field)
            print(f"Adding field: {field.name}")
            added_count += 1
        else:
            print(f"Field {field.name} already exists.")
            
    if added_count > 0:
        table.schema = new_schema
        try:
            client.update_table(table, ["schema"])
            print(f"\nSuccessfully moved table schema. Added {added_count} fields.")
        except Exception as e:
            print(f"\nFailed to update schema: {e}")
    else:
        print("\nNo schema changes needed.")

if __name__ == "__main__":
    update_schema()
