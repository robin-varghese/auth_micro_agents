# Mock Data Standards

To ensure the FinOpti platform is always demo-ready and testable without active GCP infrastructure, we maintain a `mock_data/` repository of sample artifacts.

## Directory Structure
- `mock_data/rca/`: Sample Root Cause Analysis JSON files.
- `mock_data/logs/`: Sample log snippets (JSON/Text) from Cloud Logging.
- `mock_data/metrics/`: Mocked Cloud Monitoring metric data.

## Standards for Mock Artifacts
1. **Anonymization**: Remove all PII (emails, names) and actual GCP Project IDs (use `mock-project-id`).
2. **Realism**: Logs should follow the official Cloud Logging JSON format.
3. **Traceability**: Mock RCAs should link to mock logs in the same directory using relative paths or consistent IDs.

## Example: Sample RCA JSON
```json
{
  "issue_id": "MOCK-123",
  "summary": "Service Timeout in Backend",
  "root_cause": "Database connection pool exhausted",
  "evidence": [
    {
      "type": "log",
      "source": "mock_data/logs/timeout_error.json"
    }
  ]
}
```

## How to use in Demos
When running in "Demo Mode", the Orchestrator will bypass real MCP calls and instead serve data from this directory based on predefined scenario keywords (e.g., "Troubleshoot timeout").
