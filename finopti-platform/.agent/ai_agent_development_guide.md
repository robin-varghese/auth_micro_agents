# FinOptiAgents Platform - AI Agent Development Instructions

**Version:** 1.0  
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

---

## Platform Architecture Overview

### Service Mesh Pattern
```
┌─────────────┐
│ Streamlit   │ (Port 8501)
│     UI      │
└──────┬──────┘
       │ HTTP
       ▼
┌─────────────┐
│   APISIX    │ (Port 9080) ← ALL traffic flows through here
│  Gateway    │
└──────┬──────┘
       │
   ┌───┴────────────────┐
   ▼                    ▼
┌──────────┐      ┌──────────┐
│Orchestr. │      │   OPA    │
│  Agent   │      │  Policy  │
└────┬─────┘      └──────────┘
     │
     ▼ HTTP via APISIX
┌──────────────────────────────┐
│    Sub-Agents (ADK-based)    │
│ • gcloud_agent_adk:5001      │
│ • monitoring_agent_adk:5002  │
│ • github_agent_adk:5003      │
│ • storage_agent_adk:5004     │
│ • db_agent_adk:5005          │
└────┬─────────────────────────┘
     │
     ▼ HTTP via APISIX
┌──────────────────────────────┐
│      MCP Servers             │
│ • gcloud_mcp:6001            │
│ • monitoring_mcp:6002        │
│ • github_mcp:6003            │
│ • storage_mcp:6004           │
│ • db_mcp_toolbox:5000        │
└──────────────────────────────┘
```

### Three Communication Layers

1. **Layer 1: User → Agent** (HTTP via APISIX)
   - Route: `/agent/{service_name}/*`
   - Always through APISIX

2. **Layer 2: Agent Logic** (Google ADK)
   - LLM reasoning with Gemini
   - Tool orchestration
   - Retry/reflection

3. **Layer 3: Agent → MCP** (HTTP via APISIX)
   - Route: `/mcp/{service_name}/*`
   - **MUST use HTTP, NOT stdio**

---

## Mandatory File Structure for New Agents

```
sub_agents/{agent_name}_adk/
├── agent.py           # ADK agent + HTTP MCP client
├── main.py            # Flask HTTP wrapper
├── requirements.txt   # Dependencies
├── Dockerfile         # Container build
└── README.md          # Agent documentation
```

### Required Components in Each File

#### 1. `agent.py` Structure
```python
import os
import requests  # ← Must use HTTP
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.plugins import ReflectAndRetryToolPlugin

# MCP Client - HTTP-based (NOT stdio)
class ServiceMCPClient:
    def __init__(self):
        self.apisix_url = os.getenv('APISIX_URL', 'http://apisix:9080')
        self.mcp_endpoint = f"{self.apisix_url}/mcp/{service_name}"
    
    def call_tool(self, tool_name: str, arguments: dict):
        payload = {
            "jsonrpc": "2.0",
            "method": f"tools/call",
            "params": {"name": tool_name, "arguments": arguments},
            "id": 1
        }
        response = requests.post(self.mcp_endpoint, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()

# ADK Tools (wrap MCP calls)
async def example_tool(param: str) -> dict:
    client = ServiceMCPClient()
    result = client.call_tool("mcp_tool_name", {"param": param})
    return {"success": True, "data": result}

# ADK Agent
agent = Agent(
    name="service_specialist",
    model=config.FINOPTIAGENTS_LLM,
    description="...",
    instruction="...",
    tools=[example_tool]
)

# App with Plugins
app = App(
    name=f"finopti_{service_name}_agent",
    root_agent=agent,
    plugins=[
        ReflectAndRetryToolPlugin(max_retries=2),
        BigQueryAgentAnalyticsPlugin(...)  # Optional
    ]
)
```

#### 2. `main.py` Structure
```python
from flask import Flask, request, jsonify
from agent import send_message
import os

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "{agent_name}"}), 200

@app.route('/execute', methods=['POST'])
def execute():
    data = request.get_json()
    prompt = data.get('prompt')
    user_email = data.get('user_email', 'unknown')
    
    response = send_message(prompt, user_email)
    return jsonify({
        "success": True,
        "response": response,
        "agent": "{agent_name}"
    }), 200

if __name__ == '__main__':
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
```

**DO NOT include:** `mcp>=0.1.0` (we use HTTP, not MCP stdio)

#### 4. `Dockerfile`
```dockerfile
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY sub_agents/{agent_name}_adk/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sub_agents/{agent_name}_adk/*.py .
COPY config /app/config

EXPOSE {PORT}

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
  CMD curl -f http://localhost:{PORT}/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:{PORT}", "--workers", "2", "--timeout", "120", "main:app"]
```

---

## Step-by-Step: Adding a New Agent

### Phase 1: Infrastructure Setup

#### 1.1 Add to `docker-compose.yml`
```yaml
  {agent_name}_agent:
    build:
      context: .
      dockerfile: sub_agents/{agent_name}_adk/Dockerfile
    container_name: finopti-{agent_name}-agent
    networks:
      - finopti-net
    depends_on:
      - apisix
    environment:
      GOOGLE_CLOUD_PROJECT: "${GCP_PROJECT_ID}"
      GCP_PROJECT_ID: "${GCP_PROJECT_ID}"
      APISIX_URL: "http://apisix:9080"
      GOOGLE_API_KEY: "${GOOGLE_API_KEY}"
    volumes:
      - ~/.config/gcloud:/root/.config/gcloud:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:{PORT}/health"]
      interval: 10s
      timeout: 5s
      retries: 5

  {agent_name}_mcp:
    image: {mcp_image_name}
    container_name: finopti-{agent_name}-mcp
    ports:
      - "{MCP_PORT}:{MCP_PORT}"
    networks:
      - finopti-net
```

#### 1.2 Add APISIX Routes (`apisix_conf/init_routes.sh`)
```bash
# Agent Route
echo "Creating route: /agent/{agent_name} -> {agent_name}_agent:{PORT}"
curl -i -X PUT "${APISIX_ADMIN}/routes/{ROUTE_ID}" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -d '{
    "name": "{agent_name}_agent_route",
    "uri": "/agent/{agent_name}/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {"{agent_name}_agent:{PORT}": 1}
    },
    "plugins": {
      "proxy-rewrite": {"regex_uri": ["^/agent/{agent_name}/(.*)", "/$1"]}
    }
  }'

# MCP Route
echo "Creating route: /mcp/{agent_name} -> {agent_name}_mcp:{MCP_PORT}"
curl -i -X PUT "${APISIX_ADMIN}/routes/{MCP_ROUTE_ID}" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -d '{
    "name": "{agent_name}_mcp_route",
    "uri": "/mcp/{agent_name}/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {"{agent_name}_mcp:{MCP_PORT}": 1}
    },
    "plugins": {
      "proxy-rewrite": {"regex_uri": ["^/mcp/{agent_name}/(.*)", "/$1"]}
    }
  }'
```

#### 1.3 Add OPA Policy (`opa_policy/authz.rego`)
```rego
allow if {
    user_role["gcloud_admin"]
    input.target_agent == "{agent_name}"
}
```

#### 1.4 Update Orchestrator (`orchestrator_adk/agent.py`)
```python
# In detect_intent():
{agent_name}_keywords = ['keyword1', 'keyword2', ...]
scores['{agent_name}'] = sum(1 for k in {agent_name}_keywords if k in prompt_lower)

# In route_to_agent():
agent_endpoints['{agent_name}'] = f"{config.APISIX_URL}/agent/{agent_name}/execute"
```

---

### Phase 2: Implementation

1. Create agent files using templates above
2. Implement MCP client (HTTP-based, NOT stdio)
3. Define ADK tools
4. Configure agent instruction
5. Test locally

---

### Phase 3: Verification

```bash
# 1. Build
docker-compose build {agent_name}_agent {agent_name}_mcp

# 2. Start
docker-compose up -d {agent_name}_agent {agent_name}_mcp

# 3. Apply routes
docker-compose up apisix-init

# 4. Test agent health
curl http://localhost:9080/agent/{agent_name}/health

# 5. Test MCP route
curl -X POST http://localhost:9080/mcp/{agent_name}/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'

# 6. Test end-to-end
curl -X POST http://localhost:9080/agent/{agent_name}/execute \
  -H "Content-Type: application/json" \
  -d '{"prompt":"test query","user_email":"admin@example.com"}'

# 7. Check APISIX logs (should see both agent AND mcp calls)
docker logs finopti-apisix | grep "{agent_name}"
```

---

## Common Mistakes to Avoid

### ❌ NEVER Do This

1. **Using stdio for MCP communication**
```python
# ❌ WRONG - Bypasses APISIX
from mcp.client.stdio import stdio_client
server_params = StdioServerParameters(command="docker", args=[...])
```

2. **Direct MCP server connections**
```python
# ❌ WRONG - Bypasses APISIX
requests.post("http://github_mcp:6003/", ...)
```

3. **Skipping APISIX routes**
```yaml
# ❌ WRONG - No MCP route defined
# Only agent route, MCP calls go direct
```

### ✅ ALWAYS Do This

1. **Use HTTP via APISIX**
```python
# ✅ CORRECT
requests.post(f"{APISIX_URL}/mcp/{service}/", json=payload)
```

2. **Verify routes exist**
```bash
# Check both routes are created
curl http://localhost:9180/apisix/admin/routes | grep "{agent_name}"
```

3. **Test observability**
```bash
# Ensure APISIX logs show MCP calls
docker logs finopti-apisix | grep "/mcp/{agent_name}"
```

---

## Port Assignment Convention

| Service Type | Port Range | Example |
|--------------|------------|---------|
| Agents | 5001-5099 | `gcloud_agent:5001` |
| MCP Servers | 6001-6099 | `github_mcp:6003` |
| APISIX Gateway | 9080 | Fixed |
| APISIX Admin | 9180 | Fixed |

---

## Reference Implementations

### Good Example: `gcloud_agent_adk/` (after refactoring)
- ✅ Uses Google ADK
- ✅ HTTP MCP client
- ✅ Routes through APISIX
- ✅ Full observability

### What to Study
- `docker-compose.yml`: Service definitions
- `apisix_conf/init_routes.sh`: Route patterns
- `opa_policy/authz.rego`: Authorization rules

---

## Validation Checklist

Before considering an agent "complete", verify:

- [ ] Agent uses Google ADK (`google.adk.agents.Agent`)
- [ ] MCP client uses HTTP (NOT stdio)
- [ ] MCP endpoint is `http://apisix:9080/mcp/{service}/`
- [ ] Both agent and MCP routes exist in `init_routes.sh`
- [ ] Docker Compose has both agent and MCP services
- [ ] OPA policy allows access
- [ ] Orchestrator recognizes agent keywords
- [ ] Health check passes: `curl /agent/{service}/health`
- [ ] MCP route works: `curl /mcp/{service}/`
- [ ] APISIX logs show MCP calls

---

## Questions to Ask Before Implementation

1. What is the agent's domain (GCP monitoring? Code repos? Storage?)?
2. What MCP server will it use?
3. What tools does the MCP server expose?
4. What port should the agent use (5001-5099)?
5. What port should the MCP use (6001-6099)?
6. What keywords should trigger this agent in the orchestrator?

---

## Summary

**Core Principle:** Everything flows through APISIX.

**Key Pattern:**
```
User → APISIX → ADK Agent → APISIX → MCP Server
```

**Implementation:**
- ADK for intelligence
- HTTP for transport
- APISIX for routing

**Never:**
- stdio MCP clients
- Direct MCP connections
- Bypassing the service mesh

---

**This document is the source of truth.** When in doubt, verify against existing `gcloud_agent_adk/` implementation (post-refactoring) and always route through APISIX.
