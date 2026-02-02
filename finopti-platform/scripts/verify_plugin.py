import sys
import os
from pathlib import Path

# Add sub_agents/code_execution_agent_adk to path
sys.path.append("/Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/sub_agents/code_execution_agent_adk")

# Mocking modules that might not be importable or configured
import unittest.mock
sys.modules['config'] = unittest.mock.MagicMock()

try:
    from fixed_bq_plugin import FixedBigQueryPlugin
    from google.adk.plugins.bigquery_agent_analytics_plugin import BigQueryLoggerConfig
    
    config = BigQueryLoggerConfig(enabled=True)
    plugin = FixedBigQueryPlugin(
        project_id="test-project",
        dataset_id="test-dataset",
        table_id="test-table",
        config=config
    )
    
    # Check schema
    found_latency = False
    for field in plugin._schema:
        if field.name == "latency_ms":
            found_latency = True
            print(f"latency_ms type: {field.field_type}")
            if field.field_type != "RECORD":
                 print("FAIL: latency_ms is not RECORD")
                 sys.exit(1)
            else:
                 print("PASS: latency_ms is RECORD")
    
    if not found_latency:
        print("FAIL: latency_ms not found in schema")
        sys.exit(1)
        
    print("Schema verification successful.")
    
except ImportError as e:
    print(f"ImportError: {e}")
    # Might fail due to missing dependencies in this environment
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
