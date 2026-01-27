# MATS v2.0 - API Documentation

## Orchestrator API

### POST /troubleshoot

Initiate a troubleshooting investigation.

**Request:**
```json
{
  "user_request": "My Cloud Run service 'payment-processor' is crashing",
  "project_id": "my-gcp-project",
  "repo_url": "https://github.com/myorg/myrepo",
  "user_email": "developer@example.com"  // optional
}
```

**Response (Success):**
```json
{
  "status": "SUCCESS",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "confidence": 0.85,
  "rca_url": "https://storage.cloud.google.com/mats-rca-reports/rca/550e8400.../rca_report.md",
  "rca_content": "# Root Cause Analysis\n\n...",
  "warnings": ["Version SHA not found, used 'main' branch"],
  "recommendations": ["Add integration tests", "Implement retry logic"]
}
```

**Response (Partial Success):**
```json
{
  "status": "PARTIAL",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "confidence": 0.45,
  "sre_findings": {...},
  "investigator_findings": {...},
  "error": "Low confidence in root cause",
  "recommendations": ["Human review recommended"]
}
```

**Response (Failure):**
```json
{
  "status": "FAILURE",
  "error": "Permission denied - need roles/logging.viewer"
}
```

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy"
}
```

## Investigation Workflow

1. **Planning Phase** (5-10s)
   - Sequential Thinking generates investigation plan
   - Quality gate: Plan must have valid steps

2. **Triage Phase** (30-60s)
   - SRE Agent analyzes logs/metrics
   - Extracts: timestamp, error signature, stack trace, version
   - Quality gate: Must have error_signature OR stack_trace

3. **Code Analysis Phase** (60-120s)
   - Investigator Agent reads code from GitHub
   - Maps stack trace to root cause
   - Classifies defect type
   - Quality gate: Confidence >= 0.3

4. **Synthesis Phase** (30-60s)
   - Architect Agent generates RCA markdown
   - Uploads to GCS
   - Returns signed URL
   - Quality gate: RCA must have minimum sections

**Total Duration:** 2-4 minutes (typical)

## Error Codes

| Code | Description | Recovery | Blocker |
|------|-------------|----------|---------|
| E001 | No logs found | Expand time window | No |
| E002 | Permission denied | Request IAM roles | Yes |
| E003 | Repo not accessible | Verify PAT | Yes |
| E004 | Stack trace unrecognized | Use regex extraction | No |
| E005 | Version SHA not found | Flag uncertainty | No |
| E006 | Low confidence | Suggest human review | No |

## Confidence Scores

- **1.0**: All evidence clear, definitive root cause
- **0.8-0.9**: High confidence, minor gaps
- **0.6-0.7**: Moderate confidence, some assumptions
- **0.4-0.5**: Low confidence, hypothesis only
- **<0.4**: Insufficient data

## Rate Limits

- Max 3 retry attempts per agent call
- Max 100 tool calls per investigation
- 5-minute timeout per investigation

## Authentication

When deployed behind APISIX:
```bash
curl -X POST http://localhost:9080/mats/orchestrator/troubleshoot \
  -H "Authorization: Bearer $GOOGLE_OAUTH_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_request": "Service crashing with DB errors",
    "project_id": "my-project",
    "repo_url": "https://github.com/org/repo"
  }'
```

## Monitoring

View real-time logs:
```bash
docker logs -f mats-orchestrator
```

Query BigQuery analytics:
```sql
SELECT
  session_id,
  workflow_phase,
  confidence_score,
  status
FROM `project.agent_analytics.mats_orchestrator_events`
WHERE DATE(timestamp) = CURRENT_DATE()
ORDER BY timestamp DESC
LIMIT 100
```

## Example Investigation

**Input:**
```json
{
  "user_request": "Cloud Run service 'api-server' returning 500 errors since 2pm",
  "project_id": "prod-env",
  "repo_url": "https://github.com/company/backend"
}
```

**Output:**
- Session created: `abc123`
- Plan: 3 steps (SRE → Investigator → Architect)
- SRE found: `Database connection timeout` at 14:03:21Z
- Investigator found: Missing timeout config in `database.py:45`
- Architect generated RCA with fix recommendation
- RCA URL: `https://storage.cloud.google.com/...`
- Overall confidence: 0.92
- Status: SUCCESS
