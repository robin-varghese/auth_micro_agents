# MATS v2.0 - Docker Compose Service Configuration

Add the following service to `docker-compose.yml`:

```yaml
  # ====================
  # MATS Orchestrator
  # ====================
  mats-orchestrator:
    build:
      context: .
      dockerfile: mats-agents/mats-orchestrator/Dockerfile
    container_name: mats-orchestrator
    environment:
      # Core Config
      - PORT=8080
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
      - GCP_PROJECT_ID=${GCP_PROJECT_ID}
      
      # Sequential Thinking MCP
      - SEQUENTIAL_THINKING_MCP_DOCKER_IMAGE=sequentialthinking
      - GCLOUD_MOUNT_PATH=${HOME}/.config/gcloud:/root/.config/gcloud
      
      # Team Lead Agent URLs
      - SRE_AGENT_URL=http://mats-sre-agent:8081
      - INVESTIGATOR_AGENT_URL=http://mats-investigator-agent:8082
      - ARCHITECT_AGENT_URL=http://mats-architect-agent:8083
      
      # BigQuery Analytics
      - BQ_ANALYTICS_ENABLED=true
      - BQ_ANALYTICS_DATASET=agent_analytics
      - BQ_ANALYTICS_TABLE=mats_orchestrator_events
      
    volumes:
      - ${HOME}/.config/gcloud:/root/.config/gcloud:ro
      - /var/run/docker.sock:/var/run/docker.sock  # For Docker-in-Docker (Sequential Thinking MCP)
    ports:
      - "8080:8080"
    networks:
      - finopti-net
    depends_on:
      - mats-sre-agent
      - mats-investigator-agent
      - mats-architect-agent
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

  # ====================
  # MATS SRE Agent (update existing)
  # ====================
  mats-sre-agent:
    build:
      context: .
      dockerfile: mats-agents/mats-sre-agent/Dockerfile
    container_name: mats-sre-agent
    environment:
      - PORT=8081
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
      - GCP_PROJECT_ID=${GCP_PROJECT_ID}
      - BQ_ANALYTICS_TABLE=mats_sre_events
    volumes:
      - ${HOME}/.config/gcloud:/root/.config/gcloud:ro
    ports:
      - "8081:8081"
    networks:
      - finopti-net
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8081/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

  # ====================
  # MATS Investigator Agent (update existing)
  # ====================
  mats-investigator-agent:
    build:
      context: .
      dockerfile: mats-agents/mats-investigator-agent/Dockerfile
    container_name: mats-investigator-agent
    environment:
      - PORT=8082
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
      - GITHUB_PERSONAL_ACCESS_TOKEN=${GITHUB_PERSONAL_ACCESS_TOKEN}
      - GITHUB_MCP_DOCKER_IMAGE=finopti-github-mcp-server
      - BQ_ANALYTICS_TABLE=mats_investigator_events
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock  # For GitHub MCP
    ports:
      - "8082:8082"
    networks:
      - finopti-net
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8082/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

  # ====================
  # MATS Architect Agent (update existing)
  # ====================
  mats-architect-agent:
    build:
      context: .
      dockerfile: mats-agents/mats-architect-agent/Dockerfile
    container_name: mats-architect-agent
    environment:
      - PORT=8083
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
      - GCP_PROJECT_ID=${GCP_PROJECT_ID}
      - MATS_RCA_BUCKET=${MATS_RCA_BUCKET:-mats-rca-reports}
      - BQ_ANALYTICS_TABLE=mats_architect_events
    volumes:
      - ${HOME}/.config/gcloud:/root/.config/gcloud:ro
    ports:
      - "8083:8083"
    networks:
      - finopti-net
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8083/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped
```

## APISIX Route Configuration

Add to `apisix_conf/config.yaml` routes section:

```yaml
routes:
  - id: mats_orchestrator_troubleshoot
    uri: /mats/orchestrator/troubleshoot
    upstream:
      type: roundrobin
      nodes:
        "mats-orchestrator:8080": 1
    plugins:
      prometheus:
        prefer_name: true
```

## Environment Variables

Add to `.env` file:

```bash
# MATS Configuration
MATS_RCA_BUCKET=mats-rca-reports
SEQUENTIAL_THINKING_MCP_DOCKER_IMAGE=sequentialthinking
SRE_AGENT_URL=http://mats-sre-agent:8081
INVESTIGATOR_AGENT_URL=http://mats-investigator-agent:8082
ARCHITECT_AGENT_URL=http://mats-architect-agent:8083
```
