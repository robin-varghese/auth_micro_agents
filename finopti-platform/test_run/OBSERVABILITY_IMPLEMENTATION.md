# Observability Stack Implementation Guide

## Overview

This document provides complete instructions for adding Loki + Grafana observability stack with structured logging and request ID propagation to the FinOptiAgents platform.

## ✅ What's Been Created

### 1. Observability Configuration Files

Created in `observability/` directory:

- **`loki/loki-config.yml`** - Loki configuration for log aggregation
- **`promtail/promtail-config.yml`** - Promtail configuration for log collection from Docker containers
- **`grafana/provisioning/datasources/datasources.yml`** - Grafana datasources (Loki + Prometheus)
- **`grafana/provisioning/dashboards/dash boards.yml`** - Dashboard provisioning configuration

### 2. Structured Logging Utility

Created `structured_logging.py` and copied to all services:

- **orchestrator/structured_logging.py**
- **sub_agents/gcloud_agent/structured_logging.py**
- **sub_agents/monitoring_agent/structured_logging.py**
- **mcp_servers/gcloud_mcp/structured_logging.py**
- **mcp_servers/monitoring_mcp/structured_logging.py**

### 3. Updated Orchestrator Service

Updated `orchestrator/main.py` with:
- ✅ Structured JSON logging
- ✅ Request ID generation and propagation
- ✅ Request ID added to all outgoing requests
- ✅ Request ID added to all responses
- ✅ Rich contextual information in all logs

## 🔧 Remaining Implementation Steps

### Step 1: Add Observability Services to Docker Compose

Add these services to `docker-compose.yml` after the `ui` service:

```yaml
  # ====================
  # Loki - Log Aggregation
  # ====================
  loki:
    image: grafana/loki:2.9.3
    container_name: finopti-loki
    ports:
      - "3100:3100"
    volumes:
      - ./observability/loki/loki-config.yml:/etc/loki/local-config.yaml:ro
      - loki-data:/loki
    networks:
      - finopti-net
    command: -config.file=/etc/loki/local-config.yaml
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:3100/ready"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ====================
  # Promtail - Log Collector
  # ====================
  promtail:
    image: grafana/promtail:2.9.3
    container_name: finopti-promtail
    volumes:
      - ./observability/promtail/promtail-config.yml:/etc/promtail/config.yml:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - finopti-net
    depends_on:
      - loki
    command: -config.file=/etc/promtail/config.yml

  # ====================
  # Grafana - Visualization
  # ====================
  grafana:
    image: grafana/grafana:10.2.3
    container_name: finopti-grafana
    ports:
      - "3000:3000"
    volumes:
      - ./observability/grafana/provisioning:/etc/grafana/provisioning:ro
      - grafana-data:/var/lib/grafana
    networks:
      - finopti-net
    depends_on:
      - loki
      - apisix
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: admin
      GF_USERS_ALLOW_SIGN_UP: "false"
      GF_LOG_LEVEL: info
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/api/health"]
      interval: 10s
      timeout: 5s
      retries: 5
```

And add volumes section before networks:

```yaml
# ====================
# Volume Configuration
# ====================
volumes:
  loki-data:
    name: finopti-loki-data
  grafana-data:
    name: finopti-grafana-data
```

### Step 2: Update Remaining Services

Apply the same structured logging pattern to:

#### GCloud Agent (`sub_agents/gcloud_agent/main.py`)

```python
from structured_logging import (
    StructuredLogger,
    set_request_id,
    propagate_request_id,
    add_request_id_to_response
)

# Replace logger initialization
logger = StructuredLogger('gcloud_agent', level='INFO')
app.after_request(add_request_id_to_response)

# In /execute endpoint
@app.route('/execute', methods=['POST'])
def execute():
    # Set request ID
    set_request_id(request.headers.get('X-Request-ID'))
    
    # Use structured logging
    logger.info(
        "Received execute request",
        user_email=user_email,
        prompt=prompt[:100]
    )
    
    # Propagate request ID to MCP server
    headers = propagate_request_id({"Content-Type": "application/json"})
    response = requests.post(mcp_endpoint, json=payload, headers=headers)
```

#### Monitoring Agent (`sub_agents/monitoring_agent/main.py`)

Same pattern as GCloud Agent.

#### MCP Servers

Same pattern but simpler (no OPA calls).

### Step 3: Start the Stack

```bash
# Build and start all services
docker-compose up -d --build

# Wait for services to be ready
sleep 30

# Check all services are running
docker-compose ps
```

### Step 4: Access Grafana

1. Open http://localhost:3000
2. Login with `admin` / `admin`
3. Go to "Explore"
4. Select "Loki" datasource
5. Try queries!

## 📊 Example LogQL Queries

### View All Logs
```logql
{project="finopti-platform"}
```

### Filter by Service
```logql
{service="orchestrator"}
```

### Filter by Log Level
```logql
{service="orchestrator", level="ERROR"}
```

### Filter by User
```logql
{service="orchestrator"} |= "admin@cloudroaster.com"
```

### Track Request Across Services
```logql
{project="finopti-platform"} | json | request_id="abc-123-def"
```

### Authorization Denials
```logql
{service="orchestrator"} | json | level="WARNING" | message =~ ".*denied.*"
```

### All Errors in Last Hour
```logql
{level="ERROR"} | json
```

### Request Rate by Service
```logql
rate({project="finopti-platform"} | json | method="POST" [5m])
```

## 🎯 Benefits

### 1. Centralized Logging
- All 11 services log to one place
- No need to check individual containers
- Persistent storage (survives container restarts)

### 2. Powerful Filtering
```logql
# Find all failed requests from a specific user
{service="orchestrator"} 
| json 
| user_email="admin@cloudroaster.com" 
| status_code >= 400
```

### 3. Request Tracing
```logql
# Trace entire request flow
{project="finopti-platform"} 
| json 
| request_id="550e8400-e29b-41d4-a716-446655440000"
```

Shows logs from:
- UI → APISIX → Orchestrator → OPA → Agent → MCP

### 4. Performance Monitoring
```logql
# See slow requests
{service="orchestrator"} 
| json 
| duration_ms > 1000
```

### 5. Structured Data
All logs include:
- `timestamp` - When it happened
- `level` - DEBUG/INFO/WARNING/ERROR
- `service` - Which service
- `request_id` - Trace across services
- `user_email` - Who made the request
- `target_agent` - Which agent
- `action` - What action
- `duration_ms` - How long it took
- `message` - Human-readable message

## 🔍 Sample Log Entry

```json
{
  "timestamp": "2025-12-18T18:30:00.123Z",
  "level": "INFO",
  "service": "orchestrator",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_email": "admin@cloudroaster.com",
  "target_agent": "gcloud",
  "message": "Authorization granted",
  "allowed": true
}
```

## 📈 Creating Dashboards

### Dashboard 1: Platform Overview

Panels:
1. **Request Rate** - `rate({project="finopti-platform"} [5m])`
2. **Error Rate** - `rate({level="ERROR"} [5m])`
3. **Service Health** - Count by service
4. **Recent Errors** - Table of recent ERROR logs

### Dashboard 2: Authorization Monitoring

Panels:
1. **Auth Success vs Denials** - Pie chart
2. **Denials by User** - Bar chart
3. **Denials by Agent** - Bar chart
4. **Recent Denials** - Log table

### Dashboard 3: Request Tracing

Panels:
1. **Request Duration by Service** - Histogram
2. **Request Flow** - Sankey diagram
3. **Slowest Requests** - Table

## 🚀 Quick Test

After starting the stack:

```bash
# 1. Generate some logs
curl -X POST http://localhost:9080/orchestrator/ask \
  -H "X-User-Email: admin@cloudroaster.com" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "create a VM"}'

# 2. Open Grafana
open http://localhost:3000

# 3. Go to Explore → Select Loki

# 4. Run query
{service="orchestrator"}

# 5. You should see JSON structured logs!
```

## 📝 Documentation Updates

Update `README.md` to add:

```markdown
## Observability

Access Grafana: http://localhost:3000 (admin/admin)

### View Logs
1. Open Grafana
2. Go to "Explore"
3. Select "Loki" datasource
4. Query: `{service="orchestrator"}`

### Common Queries
- All logs: `{project="finopti-platform"}`
- Errors only: `{level="ERROR"}`
- Specific user: `{service="orchestrator"} |= "admin@cloudroaster.com"`
- Request trace: `{project="finopti-platform"} | json | request_id="abc-123"`
```

## ✅ Validation Checklist

- [ ] Loki service starts successfully
- [ ] Promtail service starts successfully  
- [ ] Grafana service starts successfully
- [ ] Can access Grafana at http://localhost:3000
- [ ] Loki datasource is configured in Grafana
- [ ] Can see logs in Grafana Explore
- [ ] Logs are in JSON format
- [ ] Request ID appears in all logs for same request
- [ ] Can filter by service, level, user_email
- [ ] Can trace request across multiple services

## 🎯 Next Steps

1. **Create Custom Dashboards** - Build dashboards specific to your needs
2. **Set Up Alerting** - Alert on high error rates, authorization failures
3. **Retention Policy** - Configure log retention (currently 7 days)
4. **Log Levels** - Adjust log levels per environment (DEBUG in dev, INFO in prod)
5. **Metrics Integration** - Correlate logs with APISIX metrics in same dashboard

## 📚 Additional Resources

- [Loki Documentation](https://grafana.com/docs/loki/latest/)
- [LogQL Query Language](https://grafana.com/docs/loki/latest/logql/)
- [Grafana Dashboards](https://grafana.com/docs/grafana/latest/dashboards/)
- [Promtail Configuration](https://grafana.com/docs/loki/latest/clients/promtail/)

---

**Platform Location**: `/Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform`

**Observability Config**: `observability/` directory

**Grafana URL**: http://localhost:3000 (admin/admin)
