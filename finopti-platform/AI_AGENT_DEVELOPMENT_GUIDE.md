# FinOptiAgents Platform - AI Agent Development Instructions

**Version:** 1.2  
**Last Updated:** 2026-01-03  
**Purpose:** Mandatory guidelines for AI assistants (Gemini, Anthropic, etc.) implementing new agents

---

## ⚠️ CRITICAL ARCHITECTURE RULES

### Rule 1: ALL Traffic MUST Route Through APISIX
```
✅ CORRECT:   User → APISIX → Agent → APISIX → MCP Server
❌ INCORRECT: Agent → Direct Connection → MCP Server
❌ INCORRECT: Agent → stdio (docker run) → MCP Server
```

### Rule 2: MCP Communication MUST Use HTTP (NOT stdio)
```python
# ✅ CORRECT
requests.post(f"{APISIX_URL}/mcp/service_name/", json=payload)

# ❌ INCORRECT - DO NOT USE THIS
StdioServerParameters(command="docker", args=["run", "-i", ...])
```

### Rule 3: Use Google ADK for Agent Intelligence
All agents MUST use `google.adk.agents.Agent` for LLM orchestration.

### Rule 4: ALL Logs MUST Go to Grafana/Loki
All stdout/stderr from containers is automatically collected by Promtail and sent to Loki.  
Use structured logging for query-ability.

---

## Platform Architecture Overview

### Service Mesh Pattern
```
┌──────────────┐
│  Streamlit   │ (Port 8501) ← User authenticates via Google OAuth
│      UI      │                Gets GCP credentials
└──────┬───────┘
       │ HTTP + OAuth Token
       ▼
┌──────────────┐
│   APISIX     │ (Port 9080) ← ALL traffic flows here
│   Gateway    │               Logs to Loki via Promtail
└──────┬───────┘
       │
   ┌───┴────────────────┐
   ▼                    ▼
┌───────────┐      ┌──────────┐
│Orchestr.  │      │   OPA    │
│  Agent    │◄─────│  Policy  │ (Validates OAuth + permissions)
└─────┬─────┘      └──────────┘
      │ Uses Gemini API Key
      ▼ HTTP via APISIX
┌──────────────────────────────┐
│    Sub-Agents (ADK-based)    │ Each uses:
│ • gcloud_agent_adk:5001      │ • User's GCP credentials
│ • monitoring_agent_adk:5002  │ • Gemini API Key
│ • github_agent_adk:5003      │ • Service-specific creds (e.g. GitHub PAT)
│ • storage_agent_adk:5004     │
│ • db_agent_adk:5005          │
└────┬─────────────────────────┘
     │ Logs to stdout → Promtail → Loki
     ▼ HTTP via APISIX
┌──────────────────────────────┐
│      MCP Servers             │ Uses Gemini API Key
│ • gcloud_mcp:6001            │
│ • monitoring_mcp:6002        │
│ • github_mcp:6003            │ (Needs GitHub PAT, repo info)
│ • storage_mcp:6004           │
│ • db_mcp_toolbox:5000        │
└──────────────────────────────┘
     │ Logs to stdout → Promtail → Loki
     ▼
┌──────────────────────────────┐
│  Observability Stack         │
│ Grafana:3000 (UI)            │
│ Loki:3100 (Log aggregation)  │
│ Promtail (Log collector)     │
└──────────────────────────────┘
```

### Authentication & Credentials Flow

**1. User Authentication (Google OAuth)**
- User logs into Streamlit via Google OAuth
- OAuth provides: user email, access token
- User must have GCP credentials configured locally

**2. Agent Credentials**
```python
# Each agent receives and uses:
{
    "user_email": "user@example.com",      # From OAuth
    "google_api_key": os.getenv("GOOGLE_API_KEY"),  # For Gemini
    "gcp_credentials": "~/.config/gcloud",  # Mounted volume
    "service_specific": {...}  # e.g. GITHUB_PERSONAL_ACCESS_TOKEN
}
```

**3. GitHub MCP Specific Requirements**
```python
# GitHub MCP needs:
{
    "github_pat": os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN"),  # From Secret Manager or env
    "repo_url": "https://github.com/user/repo",  # From user or config
    "user_info": {...}  # From OAuth if available
}
```

### Three Communication Layers

1. **Layer 1: User → Agent** (HTTP via APISIX)
   - Route: `/agent/{service_name}/*`
   - Always through APISIX
   - Carries OAuth token

2. **Layer 2: Agent Logic** (Google ADK)
   - LLM reasoning with Gemini (uses `GOOGLE_API_KEY`)
   - Tool orchestration
   - Retry/reflection
   - Uses user's GCP credentials

3. **Layer 3: Agent → MCP** (HTTP via APISIX)
   - Route: `/mcp/{service_name}/*`
   - **MUST use HTTP, NOT stdio**
   - Passes service-specific credentials

---

## Google ADK Plugins (MANDATORY)

All agents MUST include two ADK plugins for proper operation, analytics, and error handling.

### Plugin 1: BigQuery Analytics Plugin

**Purpose:** Tracks all agent interactions, LLM calls, tool executions, and errors to BigQuery for analytics.

**What It Tracks:**
- User prompts and agent responses
- LLM model used and token counts
- Tool calls (parameters, results, duration)
- Errors and exceptions
- Session metadata (user_email, timestamps)

**Configuration:**
```python
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)

# Configure logging behavior
bq_config = BigQueryLoggerConfig(
    enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true\").lower() == \"true\",
    batch_size=1,  # Flush after each event (real-time tracking)
    max_content_length=100 * 1024,  # Max 100KB per event
    shutdown_timeout=10.0  # Wait 10s for pending writes on shutdown
)

# Initialize plugin
bq_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=os.getenv("GCP_PROJECT_ID"),  # Your GCP project
    dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
    table_id=os.getenv("BQ_ANALYTICS_TABLE", "agent_events_v2"),
    config=bq_config,
    location="US"  # BigQuery dataset location
)
```

**Environment Variables:**
- `BQ_ANALYTICS_ENABLED`: Enable/disable analytics (default: `true`)
- `GCP_PROJECT_ID`: GCP project for BigQuery table
- `BQ_ANALYTICS_DATASET`: BigQuery dataset name (default: `agent_analytics`)
- `BQ_ANALYTICS_TABLE`: BigQuery table name (default: `agent_events_v2`)

**BigQuery Schema:**
The plugin automatically creates a table with schema tracking:
- `timestamp`: Event time
- `user_id`: User email
- `agent_name`: Agent identifier
- `model`: LLM model used
- `prompt`: User prompt
- `response`: Agent response
- `tool_calls`: JSON array of tool executions
- `token_count`: LLM tokens used
- `error`: Error message if failed

**Querying Analytics:**
```sql
-- Most active users
SELECT user_id, COUNT(*) as request_count
FROM `project.agent_analytics.agent_events_v2`
GROUP BY user_id
ORDER BY request_count DESC;

-- Error rate by agent
SELECT agent_name, 
       COUNT(IF(error IS NOT NULL, 1, NULL)) as errors,
       COUNT(*) as total,
       ROUND(100 * COUNT(IF(error IS NOT NULL, 1, NULL)) / COUNT(*), 2) as error_rate
FROM `project.agent_analytics.agent_events_v2`
GROUP BY agent_name;

-- Average tokens per request
SELECT agent_name, AVG(token_count) as avg_tokens
FROM `project.agent_analytics.agent_events_v2`
WHERE token_count IS NOT NULL
GROUP BY agent_name;
```

---

### Plugin 2: Reflect and Retry Tool Plugin

**Purpose:** Automatically retries failed tool calls with LLM-guided error reflection.

**How It Works:**
1. Tool call fails with error
2. Plugin asks LLM to analyze the error
3. LLM suggests corrected parameters
4. Tool is retried with new parameters
5. Repeats up to `max_retries` times

**Configuration:**
```python
from google.adk.plugins import ReflectAndRetryToolPlugin

retry_plugin = ReflectAndRetryToolPlugin(
    max_retries=int(os.getenv("REFLECT_RETRY_MAX_ATTEMPTS", "3")),
    throw_exception_if_retry_exceeded=os.getenv("REFLECT_RETRY_THROW_ON_FAIL", "true").lower() == "true"
)
```

**Environment Variables:**
- `REFLECT_RETRY_MAX_ATTEMPTS`: Maximum retry attempts (default: `3`)
- `REFLECT_RETRY_THROW_ON_FAIL`: Throw exception if retries exhausted (default: `true`)

**Example Scenario:**
```
1. User: "List VMs in zone us-west1-a"
2. Agent calls: list_vms(zone="us-west1-a")
3. MCP Error: "Invalid zone: us-west1-a"
4. Retry Plugin activates:
   - Sends error to LLM: "Tool failed with 'Invalid zone'. Reflect and correct."
   - LLM suggests: {\"zone\": \"us-west1-b\"} (valid zone)
   - Retries: list_vms(zone="us-west1-b")
5. Success!
```

**Benefits:**
- ✅ Handles typos in parameters
- ✅ Fixes invalid enum values
- ✅ Corrects format errors
- ✅ Reduces user frustration
- ✅ Improves agent reliability

**Logs:**
The plugin logs retry attempts:
```
2026-01-03 20:00:00 - ReflectAndRetryToolPlugin - INFO - Tool failed: list_vms - Invalid zone
2026-01-03 20:00:01 - ReflectAndRetryToolPlugin - INFO - Retry 1/3: Reflecting on error...
2026-01-03 20:00:02 - ReflectAndRetryToolPlugin - INFO - Retry attempt with corrected params: {\"zone\": \"us-west1-b\"}
2026-01-03 20:00:03 - ReflectAndRetryToolPlugin - INFO - Retry successful!
```

---

### Combining Plugins in Agent App

**CRITICAL:** Plugin order matters!

```python
app = App(
    name=f"finopti_{service_name}_agent",
    root_agent=agent,
    plugins=[
        retry_plugin,  # MUST BE FIRST - handles tool failures
        bq_plugin      # MUST BE SECOND - tracks all events (including retries)
    ]
)
```

**Why Order Matters:**
1. `retry_plugin` wraps tool calls to add retry logic
2. `bq_plugin` tracks all events, including retry attempts
3. If reversed, retries won't be logged properly

---

### Monitoring Plugin Activity

**View in BigQuery:**
```sql
-- Find requests that required retries
SELECT prompt, tool_calls, error
FROM `project.agent_analytics.agent_events_v2`
WHERE JSON_ARRAY_LENGTH(tool_calls) > 1  -- Multiple attempts
ORDER BY timestamp DESC;
```

**View in Loki:**
```
# Find retry events
{container_name="finopti-*-agent"} |= "Retry"

# Find BigQuery write failures
{container_name="finopti-*-agent"} |= "BigQuery" |= "ERROR"
```

---

## Mandatory File Structure for New Agents

```
sub_agents/{agent_name}_adk/
├── agent.py           # ADK agent + HTTP MCP client + extensive logging
├── main.py            # Flask HTTP wrapper + structured logging
├── requirements.txt   # Dependencies
├── Dockerfile         # Container build + log config
└── README.md          # Agent documentation
```

### Required Components in Each File

#### 1. `agent.py` Structure (with Logging & Exception Handling)
```python
import os
import sys
import requests
import logging
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.plugins import ReflectAndRetryToolPlugin

# ═══════════════════════════════════════════════════════════
# LOGGING CONFIGURATION (CRITICAL - Outputs to stdout → Loki)
# ═══════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout  # ← CRITICAL: stdout is collected by Promtail
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# MCP CLIENT - HTTP-BASED WITH EXTENSIVE ERROR HANDLING
# ═══════════════════════════════════════════════════════════
class ServiceMCPClient:
    """HTTP-based MCP client that routes through APISIX"""
    
    def __init__(self, api_key: str = None, service_creds: dict = None):
        self.apisix_url = os.getenv('APISIX_URL', 'http://apisix:9080')
        self.mcp_endpoint = f"{self.apisix_url}/mcp/{service_name}"
        self.api_key = api_key or os.getenv('GOOGLE_API_KEY')
        self.service_creds = service_creds or {}
        
        logger.info(f"Initializing MCP client for {service_name}")
        logger.debug(f"MCP endpoint: {self.mcp_endpoint}")
    
    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """
        Call MCP tool via APISIX with comprehensive error handling.
        
        Args:
            tool_name: Name of the MCP tool to call
            arguments: Tool arguments
            
        Returns:
            dict: Tool response
            
        Raises:
            RuntimeError: If MCP call fails after retries
        """
        payload = {
            "jsonrpc": "2.0",
            "method": f"tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": 1
        }
        
        headers = {"Content-Type": "application/json"}
        
        # Add service-specific auth headers
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        
        # For GitHub MCP: pass PAT in header
        if service_name == "github" and "github_pat" in self.service_creds:
            headers["Authorization"] = f"Bearer {self.service_creds['github_pat']}"
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"Calling MCP tool: {tool_name} (attempt {attempt + 1}/{max_retries})")
                logger.debug(f"Payload: {payload}")
                
                response = requests.post(
                    self.mcp_endpoint,
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                
                response.raise_for_status()
                result = response.json()
                
                logger.info(f"MCP call successful: {tool_name}")
                logger.debug(f"Response: {result}")
                
                return result
                
            except requests.Timeout as e:
                logger.warning(f"MCP call timeout (attempt {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    logger.error(f"MCP call failed after {max_retries} attempts: timeout")
                    raise RuntimeError(f"MCP call timeout: {tool_name}") from e
                    
            except requests.HTTPError as e:
                logger.error(f"MCP HTTP error: {e.response.status_code} - {e.response.text}")
                raise RuntimeError(f"MCP HTTP error: {e}") from e
                
            except Exception as e:
                logger.error(f"Unexpected MCP error: {e}", exc_info=True)
                raise RuntimeError(f"MCP call failed: {e}") from e

# ═══════════════════════════════════════════════════════════
# ADK TOOLS (Wrap MCP calls with error handling)
# ═══════════════════════════════════════════════════════════
async def example_tool(param: str, user_email: str = None) -> dict:
    """
    Example ADK tool that calls MCP server.
    
    CRITICAL: All tools MUST:
    1. Log entry/exit
    2. Handle exceptions
    3. Return success/error indicators
    """
    try:
        logger.info(f"Tool called: example_tool, user: {user_email}, param: {param}")
        
        # Initialize MCP client with credentials
        service_creds = {}
        if service_name == "github":
            service_creds["github_pat"] = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
        
        client = ServiceMCPClient(service_creds=service_creds)
        
        # Call MCP
        result = client.call_tool("mcp_tool_name", {"param": param})
        
        logger.info(f"Tool completed successfully: example_tool")
        return {"success": True, "data": result}
        
    except Exception as e:
        logger.error(f"Tool failed: example_tool - {e}", exc_info=True)
        return {"success": False, "error": str(e)}

# ═══════════════════════════════════════════════════════════
# ADK AGENT CONFIGURATION
# ═══════════════════════════════════════════════════════════
agent = Agent(
    name="service_specialist",
    model=os.getenv("FINOPTIAGENTS_LLM", "gemini-3-flash-preview"),  # Uses Gemini API Key
    description="...",
    instruction=\"""
    You are a specialist for {service_name}.
    
    Authentication context:
    - You have access to the user's GCP credentials
    - Gemini API key is configured for LLM calls
    - Service-specific credentials are available (e.g., GitHub PAT)
    
    Always:
    1. Log your reasoning
    2. Handle errors gracefully
    3. Provide actionable error messages to users
    \""",
    tools=[example_tool]
)

# ═══════════════════════════════════════════════════════════
# ADK PLUGINS CONFIGURATION (MANDATORY)
# ═══════════════════════════════════════════════════════════

# Plugin 1: BigQuery Analytics (for tracking agent operations)
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)

bq_config = BigQueryLoggerConfig(
    enabled=os.getenv("BQ_ANALYTICS_ENABLED", "true").lower() == "true",
    batch_size=1,  # Number of events to batch before writing
    max_content_length=100 * 1024,  # 100KB max per event
    shutdown_timeout=10.0  # Seconds to wait for flush on shutdown
)

bq_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=os.getenv("GCP_PROJECT_ID"),
    dataset_id=os.getenv("BQ_ANALYTICS_DATASET", "agent_analytics"),
    table_id=os.getenv("BQ_ANALYTICS_TABLE", "agent_events_v2"),
    config=bq_config,
    location="US"  # BigQuery dataset location
)

logger.info(f"BigQuery Analytics Plugin configured: {bq_plugin.table_id}")

# Plugin 2: Reflect and Retry (for automatic error recovery)
retry_plugin = ReflectAndRetryToolPlugin(
    max_retries=int(os.getenv("REFLECT_RETRY_MAX_ATTEMPTS", "3")),
    throw_exception_if_retry_exceeded=os.getenv("REFLECT_RETRY_THROW_ON_FAIL", "true").lower() == "true"
)

logger.info(f"Retry Plugin configured: max_retries={retry_plugin.max_retries}")

# App with Plugins
app = App(
    name=f"finopti_{service_name}_agent",
    root_agent=agent,
    plugins=[
        retry_plugin,  # Must be first for proper error handling
        bq_plugin      # Analytics tracking
    ]
)

logger.info(f"Agent initialized: {service_name}_agent")
```

#### 2. `main.py` Structure (with Structured Logging)
```python
\"""
Flask HTTP wrapper for ADK agent.
All logs go to stdout → Promtail → Loki
\"""
from flask import Flask, request, jsonify
from agent import send_message, logger
import os
import sys

app = Flask(__name__)

# Structured logging configuration
# (Promtail scrapes stdout from docker containers)
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
main_logger = logging.getLogger(__name__)

@app.route('/health', methods=['GET'])
def health():
    \"\"\"Health check endpoint\"\"\"
    main_logger.debug("Health check called")
    return jsonify({"status": "healthy", "service": "{agent_name}"}), 200

@app.route('/execute', methods=['POST'])
def execute():
    \"\"\"
    Execute agent request.
    
    Expected payload:
    {
        "prompt": "User's request",
        "user_email": "user@example.com",  # From OAuth
        "project_id": "gcp-project-id"     # Optional
    }
    \"\"\"
    try:
        data = request.get_json()
        
        if not data:
            main_logger.error("No JSON payload received")
            return jsonify({"error": True, "message": "Missing JSON payload"}), 400
        
        prompt = data.get('prompt')
        user_email = data.get('user_email', 'unknown')
        project_id = data.get('project_id')
        
        if not prompt:
            main_logger.error("Missing prompt in request")
            return jsonify({"error": True, "message": "Missing 'prompt' field"}), 400
        
        main_logger.info(f"Processing request from {user_email}")
        main_logger.debug(f"Prompt: {prompt}")
        
        # Call ADK agent
        response = send_message(prompt, user_email, project_id)
        
        main_logger.info(f"Request completed successfully for {user_email}")
        
        return jsonify({
            "success": True,
            "response": response,
            "agent": "{agent_name}"
        }), 200
        
    except Exception as e:
        main_logger.error(f"Request failed: {e}", exc_info=True)
        return jsonify({
            "error": True,
            "message": f"Internal error: {str(e)}"
        }), 500

if __name__ == '__main__':
    main_logger.info("Starting {agent_name} agent on port {PORT}")
    app.run(host='0.0.0.0', port={PORT}, debug=False)
```

#### 3. `requirements.txt`
```txt
google-adk>=1.21.0
google-genai>=0.6.0
google-generativeai>=0.8.0
flask>=3.0.3
gunicorn>=22.0.0
requests>=2.32.4
python-dotenv>=1.0.1
google-cloud-aiplatform>=1.38.0
google-cloud-secret-manager>=2.19.0
structlog>=24.1.0  # For structured logging
```

**DO NOT include:** `mcp>=0.1.0` (we use HTTP, not MCP stdio)

#### 4. `Dockerfile` (Configured for Loki Integration)
```dockerfile
FROM python:3.11-slim
WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY sub_agents/{agent_name}_adk/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY sub_agents/{agent_name}_adk/*.py .
COPY config /app/config

# Expose port
EXPOSE {PORT}

# Healthcheck
HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
  CMD curl -f http://localhost:{PORT}/health || exit 1

# CRITICAL: Use stdout/stderr for logs (collected by Promtail)
# No file-based logging needed - Promtail scrapes container logs
ENV PYTHONUNBUFFERED=1

CMD ["gunicorn", "--bind", "0.0.0.0:{PORT}", "--workers", "2", "--timeout", "120", \
     "--access-logfile", "-", "--error-logfile", "-", "main:app"]
# ↑ CRITICAL: "-" means stdout/stderr (captured by Promtail → Loki)
```

---

## Step-by-Step: Adding a New Agent

### Phase 1: Infrastructure Setup

[... previous infrastructure setup content ...]

---

### Phase 2: Implementation

1. **Create agent files** using templates above
2. **Implement MCP client** (HTTP-based, NOT stdio)
3. **Define ADK tools with logging**
   - Log tool entry/exit
   - Log parameters (sanitize secrets!)
   - Handle exceptions with detailed error messages
4. **Configure agent instruction**
   - Include authentication context
   - Specify credential requirements
5. **Add comprehensive logging**
   - Use `logging.info()` for flow
   - Use `logging.debug()` for detailed data
   - Use `logging.error()` with `exc_info=True` for exceptions
6. **Test locally** with verbose logging

---

### Phase 3: Testing & Documentation

#### 3.1 Create Test Scripts
**File:** `scripts/test_sui/test_{agent_name}_agent.py`
```python
\"\"\"Test script for {agent_name} agent\"\"\"
import requests
import json

def test_agent_health():
    \"\"\"Test agent health endpoint\"\"\"
    response = requests.get("http://localhost:9080/agent/{agent_name}/health")
    assert response.status_code == 200
    print("✓ Health check passed")

def test_agent_execution():
    \"\"\"Test agent execution\"\"\"
    payload = {
        "prompt": "Test query",
        "user_email": "test@example.com"
    }
    response = requests.post(
        "http://localhost:9080/agent/{agent_name}/execute",
        json=payload
    )
    assert response.status_code == 200
    result = response.json()
    assert result.get("success") == True
    print(f"✓ Execution test passed: {result}")

if __name__ == "__main__":
    test_agent_health()
    test_agent_execution()
    print("All tests passed!")
```

#### 3.2 Run Test Suite
```bash
# Run tests
python3 scripts/test_sui/test_{agent_name}_agent.py > test_results_{agent_name}.txt 2>&1

# Check results
cat test_results_{agent_name}.txt
```

#### 3.3 Update Test Runner
**File:** `scripts/test_sui/run_all_tests.py`
```python
# Add new agent test
from test_{agent_name}_agent import test_agent_health, test_agent_execution

def run_all_tests():
    # ... existing tests ...
    
    print("\\n=== Testing {agent_name} Agent ===")
    test_agent_health()
    test_agent_execution()
```

#### 3.4 Update README.md
Add section for new agent:
```markdown
### {AgentName} Agent

**Port:** {PORT}  
**MCP Server:** {mcp_name}:{MCP_PORT}  
**Purpose:** {Brief description}

**Authentication:**
- Requires: {list credentials needed}
- Example: GITHUB_PERSONAL_ACCESS_TOKEN for GitHub agent

**APISIX Routes:**
- Agent: `/agent/{agent_name}/*` → `{agent_name}_agent:{PORT}`
- MCP: `/mcp/{agent_name}/*` → `{agent_name}_mcp:{MCP_PORT}`

**Testing:**
bash
python3 scripts/test_sui/test_{agent_name}_agent.py
```

**Logs:**
View in Grafana:
- URL: http://localhost:3000
- Query: `{container_name="finopti-{agent_name}-agent"}`
```

---

### Phase 4: Observability Verification

**Verify Logs in Grafana/Loki:**
```bash
# 1. Access Grafana
open http://localhost:3000

# 2. Navigate to Explore → Loki

# 3. Query agent logs
{container_name="finopti-{agent_name}-agent"}

# 4. Filter for errors
{container_name="finopti-{agent_name}-agent"} |= "ERROR"

# 5. Check MCP calls
{container_name="finopti-{agent_name}-agent"} |= "Calling MCP tool"

# 6. Verify APISIX routing
{container_name="finopti-apisix"} |= "/mcp/{agent_name}"
```

**Expected Log Flow:**
```
finopti-apisix         → "POST /agent/{agent_name}/execute"
finopti-{agent_name}-agent → "Processing request from user@example.com"
finopti-{agent_name}-agent → "Calling MCP tool: tool_name"
finopti-apisix         → "POST /mcp/{agent_name}/"
finopti-{agent_name}-mcp → "Tool executed: tool_name"
```

**Troubleshooting via Loki:**
```
# Check authentication issues
{container_name=~"finopti-.*"} |= "401" or |= "403"

# Check timeout issues
{container_name=~"finopti-.*"} |= "timeout"

# Check MCP connection errors
{container_name=~"finopti-.*"} |= "MCP" |= "ERROR"
```

---

## Validation Checklist

Before considering an agent "complete", verify:

**Code Quality:**
- [ ] Agent uses Google ADK (`google.adk.agents.Agent`)
- [ ] MCP client uses HTTP (NOT stdio)
- [ ] Extensive logging in all functions (entry/exit/errors)
- [ ] Exception handling with detailed error messages
- [ ] Logging outputs to stdout (verified via `docker logs`)

**Infrastructure:**
- [ ] MCP endpoint is `http://apisix:9080/mcp/{service}/`
- [ ] Both agent and MCP routes exist in `init_routes.sh`
- [ ] Docker Compose has both agent and MCP services
- [ ] OPA policy allows access
- [ ] Orchestrator recognizes agent keywords

**Credentials:**
- [ ] Gemini API key configured (`GOOGLE_API_KEY`)
- [ ] GCP credentials mounted (`~/.config/gcloud`)
- [ ] Service-specific credentials documented (e.g., GitHub PAT)
- [ ] OAuth user email passed to agent

**Testing:**
- [ ] Health check passes: `curl /agent/{service}/health`
- [ ] MCP route works: `curl /mcp/{service}/`
- [ ] Test script created in `scripts/test_sui/`
- [ ] Test results recorded
- [ ] All tests pass

**Observability:**
- [ ] APISIX logs show agent calls
- [ ] APISIX logs show MCP calls
- [ ] Agent logs visible in Grafana/Loki
- [ ] MCP logs visible in Grafana/Loki
- [ ] Error logs are query-able in Loki

**Documentation:**
- [ ] README.md updated with new agent section
- [ ] Authentication requirements documented
- [ ] Example usage provided
- [ ] Observability query examples added

---

## Common Mistakes to Avoid

### ❌ NEVER Do This

1. **Using stdio for MCP** (bypasses APISIX)
2. **Logging to files** (use stdout → Promtail)
3. **Ignoring exceptions** (must log with exc_info=True)
4. **Skipping tests** (must have test script)
5. **Not updating README** (documentation is mandatory)

### ✅ ALWAYS Do This

1. **Use HTTP via APISIX** for MCP calls
2. **Log to stdout** (Promtail collects)
3. **Handle exceptions** with detailed logging
4. **Create test scripts** and record results
5. **Update README** with new agent details

---

## Summary

**Core Principle:** Everything flows through APISIX, all logs go to Loki.

**Authentication Flow:**
```
Google OAuth → User Email + GCP Creds → Agent (uses Gemini API Key) → MCP (uses service creds)
```

**Logging Flow:**
```
Container stdout → Promtail → Loki → Grafana (query/visualize)
```

**Implementation Checklist:**
1. HTTP MCP client (not stdio)
2. Extensive logging (stdout)
3. Exception handling
4. Test scripts
5. README updates
6. Loki verification

---

## Troubleshooting with Observability Stack

### Philosophy: Logs First, Code Second

The platform's observability stack (Promtail → Loki → Grafana + APISIX logs) provides **complete visibility** into all requests. When debugging issues, **ALWAYS start with logs** before looking at code.

---

### Step-by-Step Troubleshooting Process

#### 1. Identify the Failed Request

When a user reports an error (e.g., "Expecting value: line 1 column 1 (char 0)"), start here:

```bash
# Check APISIX access logs for recent errors
docker logs finopti-apisix --tail 50 | grep -E "(ERROR|50[0-9]|40[0-9])"
```

**What to look for:**
- HTTP error codes: `502`, `503`, `504` (upstream issues)
- `Connection refused` (service down or wrong port)
- `404` (route not configured)
- `timeout` (slow upstream service)

#### 2. Trace the Request Path

Use the service mesh architecture to trace the request:

```
User → APISIX → Orchestrator → APISIX → Agent → APISIX → MCP
```

Check logs at each hop:

```bash
# Step 1: Check if request reached APISIX
docker logs finopti-apisix | tail -30 | grep "/orchestrator/ask"

# Step 2: Check orchestrator logs
docker logs finopti-orchestrator --tail 50 | grep -E "(ERROR|vector-search-poc)"

# Step 3: Check specific agent (e.g., gcloud)
docker logs finopti-gcloud-agent --tail 50 | grep -E "(ERROR|MCP)"

# Step 4: Check APISIX logs for MCP routing
docker logs finopti-apisix | tail -30 | grep "/mcp/"
```

#### 3. Find Root Cause Using Log Patterns

**Pattern 1: Connection Refused**
```
APISIX ERROR: connect() failed (111: Connection refused) 
while connecting to upstream: http://172.20.0.9:15000/ask
```

**Root Cause:** Wrong port configuration in APISIX route
**Fix:** Check `apisix_conf/init_routes.sh` - verify upstream port matches service port

**Pattern 2: Timeout**
```
Agent ERROR: MCP call timeout (attempt 3/3): ReadTimeout
```

**Root Cause:** MCP server not responding or slow
**Fix:** 
1. Check MCP server is running: `docker ps | grep mcp`
2. Increase timeout in agent MCP client
3. Check MCP server logs for errors

**Pattern 3: JSON Parsing Error**
```
ERROR: Expecting value: line 1 column 1 (char 0)
```

**Root Cause:** Empty response or non-JSON response from upstream
**Fix:** Check previous error in chain - likely upstream service failing

**Pattern 4: 404 Not Found (APISIX)**
```
{"error_msg":"404 Route Not Found"}
```

**Root Cause:** APISIX route not configured
**Fix:** 
1. Check route exists: `curl http://localhost:9180/apisix/admin/routes -H "X-API-KEY: finopti-admin-key"`
2. Add route in `apisix_conf/init_routes.sh`
3. Restart: `docker-compose up apisix-init`

#### 4. Real-World Example: "List VMs" Error

**User Error:**
```
"List all VMs in gcp project vector-search-poc"
❌ Error: Expecting value: line 1 column 1 (char 0)
```

**Troubleshooting Process:**

1. **Check APISIX logs:**
```bash
docker logs finopti-apisix | tail -30
```

**Found:**
```
connect() failed (111: Connection refused) 
while connecting to upstream: http://172.20.0.9:15000/ask
```

2. **Identify the issue:**
- APISIX trying to connect to orchestrator on port **15000**
- Orchestrator actually runs on port **5000**

3. **Check docker status:**
```bash
docker ps | grep orchestrator
# finopti-orchestrator   Up 4 hours (healthy)   5000/tcp
```

4. **Root cause:** APISIX route configuration has wrong port

5. **Fix:**
```bash
# Edit apisix_conf/init_routes.sh
# Change: "orchestrator:15000"
# To:     "orchestrator:5000"

# Apply fix
docker-compose up apisix-init
```

**Time to diagnose:** 30 seconds using observability  
**Alternative without logs:** 30+ minutes of guessing

---

### Common Issues & Quick Fixes

| Error | Check | Fix |
|-------|-------|-----|
| `Connection refused` | `docker logs finopti-apisix` | Verify upstream port in APISIX route |
| `502 Bad Gateway` | `docker ps --filter "name=<service>"` | Restart service or check health |
| `404 Not Found` | APISIX routes | Add missing route in `init_routes.sh` |
| `timeout` | MCP server logs | Check MCP responsiveness, increase timeout |
| JSON parse error | Upstream logs | Check for empty/non-JSON responses |
| MCP stdio errors | Agent code | Verify using HTTP client, not stdio |

---

### Grafana/Loki Queries for Troubleshooting

#### View All Recent Errors
```logql
{project="finopti-platform"} |= "ERROR"
```

#### Track Specific Request by User
```logql
{container_name=~"finopti-.*"} |= "robin@cloudroaster.com"
```

#### Find MCP Routing Issues
```logql
{container_name=~"finopti-apisix"} |= "/mcp/" | grep "50[0-9]"
```

#### See Agent → MCP Communication
```logql
{container_name=~"finopti-.*-agent"} |= "MCP call"
```

#### Check APISIX Upstream Failures
```logql
{container_name="finopti-apisix"} |= "upstream"
```

---

### Debugging Checklist

When troubleshooting ANY issue:

- [ ] **Check APISIX logs first** - Find HTTP errors and routing failures
- [ ] **Verify service is running** - `docker ps | grep <service>`
- [ ] **Check service logs** - `docker logs <container-name> --tail 50`
- [ ] **Trace request path** - User → APISIX → Service1 → APISIX → Service2
- [ ] **Verify APISIX routes** - Correct upstream host:port
- [ ] **Check credentials** - API keys, tokens in environment/Secret Manager
- [ ] **Use Grafana** - Query Loki for patterns across services
- [ ] **Check MCP routing** - Verify agents use HTTP via APISIX (not stdio)

---

### Pro Tips

1. **Always enable verbose logging during development:**
```bash
export LOG_LEVEL=DEBUG
docker-compose up -d <service>
```

2. **Use request IDs to trace across services:**
```logql
{project="finopti-platform"} | json | request_id="<request-id>"
```

3. **Monitor APISIX metrics:**
```bash
curl http://localhost:9091/apisix/prometheus/metrics | grep apisix_http_status
```

4. **Check health endpoints:**
```bash
curl http://localhost:9080/agent/gcloud/health
curl http://localhost:9080/orchestrator/health
```

5. **Validate APISIX routes after changes:**
```bash
docker-compose up apisix-init
# Check logs for "All routes initialized successfully!"
```

---

## Summary

**This document is the source of truth.** When in doubt, verify against existing `gcloud_agent_adk/` implementation (post-refactoring) and always route through APISIX.
