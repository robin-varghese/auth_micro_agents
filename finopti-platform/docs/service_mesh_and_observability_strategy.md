# Strategy: Service Mesh & Full Observability

## 1. Executive Summary

The FinOptiAgents platform currently operates on a "Gateway" architecture where APISIX acts as a central router. The user vision is to evolve this into a **Service Mesh** pattern where all service-to-service communication is strictly mediated, observed, and controlled. Simultaneously, the platform contains dormant Observability components (Loki, Promtail, Grafana) that need to be activated to provide a "Single Pane of Glass" for debugging and monitoring.

This document outlines the strategy to:
1.  **Enforce Service Mesh Architecture**: Ensure *all* traffic (East-West and North-South) transit through the APISIX layer.
2.  **Enable Full Observability**: Activate the PLG (Promtail, Loki, Grafana) stack to ingest logs and metrics from all containers.

---

## 2. Service Mesh Architecture Strategy

### Current State
*   **Pattern**: Hub-and-Spoke / API Gateway.
*   **Flow**: UI → APISIX → Orchestrator → Agents.
*   **Gap**: While Orchestrator uses APISIX to call Agents, there is potential for direct container-to-container bypassing (e.g., via Docker bridge IP). The "Mesh" concept is loose.

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

### Phase 1: Activate Observability (Immediate Value)
The code exists. We will activate it to give developers immediate visibility.

1.  **Update `docker-compose.yml`**:
    *   Add `loki`, `promtail`, `grafana` services.
    *   Mount `promtail-config.yml` and `datasources.yml`.
2.  **Verify Log Pipeline**:
    *   Ensure Promtail can read Docker socket.
    *   Ensure Loki ingests streams.
3.  **Deploy Dashboards**:
    *   Provision the "FinOptiAgents Debugger" dashboard.

### Phase 2: Enforce Service Mesh
Harden the networking.

1.  **Network Isolation**:
    *   Remove `ports` based exposure for backend agents (hide `:5001`, `:5002`).
    *   Expose ONLY via APISIX routes.
2.  **Traffic Policies**:
    *   Apply `limit-count` and `api-breaker` plugins to Agent routes in APISIX.

### Phase 3: Advanced Mesh Features (Future)
1.  **Canary Deployments**: Weighted routing for updating Agents.
2.  **Fault Injection**: Test Orchestrator resilience by injecting delays via media.

---

This strategy moves FinOptiAgents from a "Working Prototype" to a "Production-Ready Platform" with deep visibility and robust networking.
