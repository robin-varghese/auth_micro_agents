from google.adk.plugins.bigquery_agent_analytics_plugin import BigQueryAgentAnalyticsPlugin
from google.cloud import bigquery

class FixedBigQueryPlugin(BigQueryAgentAnalyticsPlugin):
    """
    Subclass of BigQueryAgentAnalyticsPlugin to enforce specific schema definitions.
    This fixes issues where the upstream plugin might miss fields or define them with
    conflicting types (e.g., STRING instead of RECORD for latency_ms).
    """
    def __init__(self, *args, **kwargs):
        import logging
        import google.adk.plugins.bigquery_agent_analytics_plugin as bq_plugin_module
        from google.cloud import bigquery
        
        logger = logging.getLogger(__name__)
        
        # Explicitly define the full schema
        full_schema = [
            bigquery.SchemaField("timestamp", "TIMESTAMP"),
            bigquery.SchemaField("event_type", "STRING"),
            bigquery.SchemaField("agent", "STRING"),
            bigquery.SchemaField("user_id", "STRING"),
            bigquery.SchemaField("session_id", "STRING"),
            bigquery.SchemaField("invocation_id", "STRING"),
            bigquery.SchemaField("trace_id", "STRING"),
            bigquery.SchemaField("span_id", "STRING"),
            bigquery.SchemaField("parent_span_id", "STRING"),
            bigquery.SchemaField("content", "STRING"), # Can be JSON string or text
            
            # Explicitly define content_parts as REPEATED RECORD
            bigquery.SchemaField("content_parts", "RECORD", mode="REPEATED", fields=[
                bigquery.SchemaField("part_index", "INTEGER"),
                bigquery.SchemaField("mime_type", "STRING"),
                bigquery.SchemaField("uri", "STRING"),
                bigquery.SchemaField("text", "STRING"),
                bigquery.SchemaField("part_attributes", "STRING"), # JSON str
                bigquery.SchemaField("storage_mode", "STRING"),
                bigquery.SchemaField("object_ref", "STRING"),
            ]),
            
            bigquery.SchemaField("attributes", "STRING"), # JSON string
            
            # FIX: Explicitly define latency_ms as RECORD
            bigquery.SchemaField("latency_ms", "RECORD", fields=[
                bigquery.SchemaField("total_ms", "INTEGER"),
                bigquery.SchemaField("time_to_first_token_ms", "INTEGER"),
            ]),
            
            bigquery.SchemaField("status", "STRING"),
            bigquery.SchemaField("error_message", "STRING"),
            bigquery.SchemaField("is_truncated", "BOOLEAN"),
        ]

        logger.info("FixedBigQueryPlugin: Preparing to monkeypatch to_arrow_schema...")

        # 1. Generate the CORRECT Arrow schema using our explicit BQ schema
        try:
            correct_arrow_schema = bq_plugin_module.to_arrow_schema(full_schema)
            logger.info("FixedBigQueryPlugin: Generated correct Arrow schema for patching.")
        except Exception as e:
            logger.error(f"FixedBigQueryPlugin: Failed to generate Arrow schema: {e}")
            # Fallback - proceed without patch, though it will likely fail
            correct_arrow_schema = None

        # 2. Monkeypatch the module function
        original_to_arrow_schema = getattr(bq_plugin_module, 'to_arrow_schema', None)
        
        if correct_arrow_schema and original_to_arrow_schema:
            def patched_to_arrow_schema(schema):
                logger.info("FixedBigQueryPlugin: patched_to_arrow_schema called! Returning corrected schema.")
                return correct_arrow_schema
            
            bq_plugin_module.to_arrow_schema = patched_to_arrow_schema
            logger.info("FixedBigQueryPlugin: Monkeypatch applied.")
        else:
            logger.warning("FixedBigQueryPlugin: Could not apply monkeypatch (missing schema or function).")

        # 3. Initialize the base class (which will now use the patched function)
        try:
            super().__init__(*args, **kwargs)
            logger.info("FixedBigQueryPlugin: super().__init__ completed.")
        finally:
            # 4. Restore original function
            if original_to_arrow_schema:
                bq_plugin_module.to_arrow_schema = original_to_arrow_schema
                logger.info("FixedBigQueryPlugin: Monkeypatch restored.")

        # 5. Ensure the plugin instance also has the correct BQ schema
        self._schema = full_schema
        logger.info("FixedBigQueryPlugin: self._schema explicitly set.")
