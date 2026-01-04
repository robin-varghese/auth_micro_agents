# Strategy: Service Mesh & Full Observability

## 1. Executive Summary

The FinOptiAgents platform currently operates on a "Gateway" architecture where APISIX acts as a central router. The user vision is to evolve this into a **Service Mesh** pattern where all service-to-service communication is strictly mediated, observed, and controlled. Simultaneously, the platform contains dormant Observability components (Loki, Promtail, Grafana) that need to be activated to provide a "Single Pane of Glass" for debugging and monitoring.

This document outlines the strategy to:
1.  **Enforce Service Mesh Architecture**: Ensure *all* traffic (East-West and North-South) transit through the APISIX layer.
2.  **Enable Full Observability**: Activate the PLG (Promtail, Loki, Grafana) stack to ingest logs and metrics from all containers.

---
config:
  layout: fixed
---
flowchart TB
    User["Streamlit UI<br>Port 8501"] --> APISIX["Apache APISIX"]
    APISIX --> Orchestrator["Orchestrator Agent"] & n2["Loki"]
    Orchestrator --> OPA["OPA Sidecar<br>"] & n1["APISIX"] & n2
    Monitoring["Monitoring Agent"] --> APISIX2["APISIX"] & n2
    APISIX2 --> GCloudMCP["GCloud MCP"] & MonitoringMCP["Monitoring MCP"] & n2
    n1 --> GCloud["GCloud Agent"] & Monitoring & n2
    GCloud --> APISIX2 & n2
    GCloudMCP --> n2
    MonitoringMCP --> n2
    n3["All Logs"]

    n2@{ shape: rect}
    n1@{ shape: rect}
    n3@{ shape: text}
    linkStyle 2 stroke:#2962FF,fill:none
    linkStyle 5 stroke:#2962FF,fill:none
    linkStyle 7 stroke:#2962FF,fill:none
    linkStyle 10 stroke:#2962FF,fill:none
    linkStyle 13 stroke:#2962FF,fill:none
    linkStyle 15 stroke:#2962FF,fill:none
    linkStyle 16 stroke:#2962FF,fill:none
    linkStyle 17 stroke:#2962FF,fill:none

## 2. Service Mesh Architecture Strategy


### Current State (v1.1.0 - Updated 2026-01-04)
*   **Pattern**: **Full Service Mesh** with APISIX as Data Plane ✅
*   **Flow**: UI → APISIX → Orchestrator → APISIX → Agents → APISIX → MCPs
*   **Achievement**: **100% of traffic** now routes through APISIX gateway
*   **MCP Communication**: All 5 agents (gcloud, monitoring, github, storage, db) use HTTP via APISIX
*   **Observability**: Complete visibility of all inter-service communication in APISIX logs and Loki
*   **Consistency**: Zero direct container-to-container communication - strict service mesh enforcement

#### ✅ Completed Migration (Jan 2026)
All ADK-based agents refactored from stdio/direct HTTP to APISIX routing:
- `github_agent_adk`: stdio → HTTP via `/mcp/github/*`
- `storage_agent_adk`: stdio → HTTP via  `/mcp/storage/*`
- `db_agent_adk`: direct HTTP → HTTP via `/mcp/db/*`
- `gcloud_agent_adk`: stdio → HTTP via `/mcp/gcloud/*`
- `monitoring_agent_adk`: stdio → HTTP via `/mcp/monitoring/*`


### Target State
A strict **Service Mesh** implementation using APISIX as the Data Plane.

#### 1. Universal Proxying
*   **Rule**: No service should communicate directly with another service's internal port. All calls must target the APISIX Gateway.
*   **Mechanism**: 
    *   Services expose ports ONLY to the APISIX container (via Docker network isolation or explicit `expose` vs `ports` mapping).
    *   Applications perform DNS lookups against the Mesh (APISIX) rather than the service name.

#### 2. Traffic Control
*   **Circuit Breaking**: Configure APISIX upstreams to handle Agent failures gracefully (e.g., if GCloud agent is slow, fail fast).
*   **Retries**: Centralize retry logic in APISIX routes rather than application code.
*   **Rate Limiting**: Protect Agents from Orchestrator floods using APISIX plugins.

#### 3. Security (Zero Trust)
*   **mTLS (Optional Future)**: Encrypt traffic between Orchestrator and Agents.
*   **Policy Enforcement**: Move OPA checks strictly to the Gateway/Sidecar level, removing creating a unified "Authorization Sidecar" pattern.

---

## 3. Observability Strategy (The "Missing" Piece)

### Current State
*   **Components**: Code exists in `observability/` (Promtail config, Loki config, Grafana provision).
*   **Status**: Dormant. Not explicitly running in `docker-compose.yml`.
*   **Gap**: Logs are trapped in containers (`docker logs`). No centralized visualization.

### Target State
A **Full PLG Stack** (Promtail, Loki, Grafana) integrated with APISIX Tracing.

#### 1. Log Aggregation (Loki + Promtail)
*   **Promtail**: Deployed as a daemon to scrape `var/lib/docker/containers/*/*.log`.
*   **Processing**:
    *   Parse JSON logs from Applications (Orchestrator, Agents).
    *   Extract `trace_id` and `span_id`.
    *   Label logs by `service` (`orchestrator`, `gcloud_agent`).
*   **Loki**: Acts as the central index-free log database.

#### 2. Visualization (Grafana)
*   **Datasources**:
    *   **Loki**: For logs.
    *   **Prometheus**: For APISIX metrics (request count, latency).
*   **Dashboards**:
    *   **Platform Overview**: RED metrics (Rate, Errors, Duration) from APISIX.
    *   **Trace View**: A dashboard that takes a `trace_id` and filters logs from *all* services to visualize the request lifecycle.
    *   **Debug Console**: A "Log Stream" view for developers to watch live system behavior.

#### 3. Distributed Tracing
*   **APISIX**: Generates `X-Request-Id` (or OpenTelemetry headers).
*   **Services**: Propagate these headers (already implemented in `structured_logging.py`).
*   **Correlation**: Grafana links logs to metrics using these IDs.

---

## 4. Implementation Roadmap

### ✅ Phase 1: Activate Observability (COMPLETE - Jan 2026)
1.  ✅ **Updated `docker-compose.yml`**: Added `loki`, `promtail`, `grafana` services
2.  ✅ **Verified Log Pipeline**: Promtail collects from Docker, Loki ingests, Grafana visualizes
3.  ✅ **Deployed Dashboards**: Platform observability dashboards operational

### ✅ Phase 2: Enforce Service Mesh (COMPLETE - Jan 2026)
1.  ✅ **MCP Routing**: All agents refactored to route MCP calls via APISIX
2.  ✅ **HTTP Migration**: Migrated from stdio (docker spawn) to persistent HTTP connections
3.  ✅ **APISIX Routes**: Added routes 9-11 for github/storage/db MCP servers
4.  ✅ **Full Observability**: 100% of traffic visible in APISIX logs and Loki

### Phase 3: Advanced Mesh Features (Future)
1.  **Traffic Policies**: Apply `limit-count` and `api-breaker` plugins to MCP routes
2.  **Canary Deployments**: Weighted routing for updating MCPs/Agents
3.  **Fault Injection**: Test resilience by injecting delays via APISIX
4.  **mTLS**: Encrypt all east-west traffic

---

This strategy moves FinOptiAgents from a "Working Prototype" to a "Production-Ready Platform" with deep visibility and robust networking.

---


## 📝 Document History

| Version | Date       | Author | Revision Summary |
|---------|------------|--------|------------------|
| 1.2.0   | 2026-01-04 | Antigravity AI | Updated to reflect completed Service Mesh implementation with full APISIX MCP routing. |
| 1.1.0   | 2026-01-01 | Antigravity AI | Added Service Mesh architectural diagram and implementation details. |
