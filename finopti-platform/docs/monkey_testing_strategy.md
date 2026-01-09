# Chaos Monkey Testing Application Strategy (Implemented)

## 🎯 Objective
The **Monkey Testing Web Application** orchestrates controlled disruptions (chaos engineering) on the target Cloud Run service (`calculator-app`). It provides a user-friendly interface to trigger 10 distinct failure scenarios and verify the system's resilience and self-healing capabilities via the MATS (Multimodal Autonomous Troubleshooting System) agents.

**Target Application:**
*   **Service Name**: `calculator-app`
*   **Region**: `us-central1`
*   **Project**: `vector-search-poc`
*   **Image**: `us-central1-docker.pkg.dev/vector-search-poc/cloud-run-source-deploy/calculator-app`

## 🏗️ Architecture Design

The solution is fully integrated into the `finopti-platform` ecosystem.

### 1. Components

#### 🐵 Monkey UI (Frontend)
*   **Tech Stack**: Vanilla HTML/CSS/JS served by Nginx.
*   **Location**: `auth_micro_agents/chaos-monkey-testing/monkey_ui/`
*   **Functionality**:
    *   Dashboard displaying 10 scenarios.
    *   **Simulate �**: Triggers the `break_prompt`.
    *   **Restore 🟢**: Triggers the `restore_prompt`.
    *   **Live Logs**: Displays the natural language response from the Orchestrator.

#### 🧠 Monkey Agent (Backend)
*   **Tech Stack**: Python (Flask).
*   **Location**: `auth_micro_agents/chaos-monkey-testing/monkey_agent/`
*   **Port**: 5007
*   **Endpoints**:
    *   `GET /scenarios`: Returns list of available chaos scenarios.
    *   `POST /execute`: Accepts `{id, action}` and forwards the prompt to the Orchestrator.
*   **Integration**: Calls `http://apisix:9080/orchestrator/ask` to trigger agentic workflows.

#### 🌩️ Cloud Run Agent (The Executor)
*   **Tech Stack**: Python (Google ADK).
*   **Location**: `auth_micro_agents/finopti-platform/sub_agents/cloud_run_agent_adk/`
*   **Execution Model**: 
    *   Originally designed to use an MCP Server.
    *   **Current Implementation**: Uses direct `subprocess` calls to the `gcloud` CLI installed in the container for maximum reliability and feature coverage.
    *   **Filesystem Workaround**: Copies read-only mounted gcloud configuration to `/tmp/gcloud_config` at runtime to allow write operations (lock files, logs).

### 2. Communication Flow
1.  **User** clicks "Simulate" on Monkey UI.
2.  **Monkey UI** sends `POST /execute` to Monkey Agent.
3.  **Monkey Agent** looks up the `break_prompt` for the scenario.
4.  **Monkey Agent** sends the prompt to **FinOpti Orchestrator** via APISIX.
5.  **Orchestrator** routes the request to **Cloud Run Agent**.
6.  **Cloud Run Agent** translates the prompt into a `gcloud run` command and executes it locally.
7.  **Result** is returned up the chain to the User.

---

## 💥 Implemented Chaos Scenarios

The following 10 scenarios are defined in `monkey_agent/scenarios.py` and actively running.

### 1. Service Blackout (Total Destruction)
*   **Action**: `gcloud run services delete calculator-app ...`
*   **Impact**: 404 Not Found. Service completely removed.
*   **Restore**: Redeploys the service using the Artifact Registry image.

### 2. Auth Lockdown (Permission Denied)
*   **Action**: Removes `roles/run.invoker` from `allUsers`.
*   **Impact**: 403 Forbidden for public users.
*   **Restore**: Re-grants `roles/run.invoker` to `allUsers`.

### 3. Broken Deployment (CrashLoopBackOff)
*   **Action**: Deploys `gcr.io/google-containers/pause:1.0` (simulating a bad image).
*   **Impact**: 503 Service Unavailable / Deployment Failure.
*   **Restore**: Redeploys the correct `calculator-app` image.

### 4. Traffic Void (Misrouting)
*   **Action**: Sets traffic to 0% (or routes to non-existent revision).
*   **Impact**: 404 or 503 depending on implementation.
*   **Restore**: Routes 100% traffic to `LATEST`.

### 5. Resource Starvation (OOM Kill)
*   **Action**: Sets memory limit to `64Mi`.
*   **Impact**: Container crashes with "Memory limit exceeded" under load.
*   **Restore**: Sets memory limit back to `512Mi`.

### 6. Concurrency Freeze (Latency Spike)
*   **Action**: Sets `concurrency=1` and `max-instances=1`.
*   **Impact**: Massive request queuing and high latency (504s).
*   **Restore**: Resets concurrency to default (80).

### 7. Bad Environment (Config Failure)
*   **Action**: Injects `DB_CONNECTION_STRING=invalid_host:5432`.
*   **Impact**: Application logic fails (500 Internal Server Error) when trying to connect.
*   **Restore**: Removes the invalid environment variable.

### 8. Network Isolation (Ingress Restriction)
*   **Action**: Sets ingress to `internal`.
*   **Impact**: 403 Forbidden (or 404) for external traffic.
*   **Restore**: Sets ingress to `all`.

### 9. Cold Start Freeze (Scale to Zero)
*   **Action**: Sets `min-instances=0` and `max-instances=0`.
*   **Impact**: Service is effectively suspended; will not scale up for requests.
*   **Restore**: Sets `min-instances=1` (warm) and removes max limit.

### 10. Region Failover (Disaster Recovery)
*   **Action**: Deletes from `us-central1` AND deploys to `us-west1`.
*   **Impact**: Service available but with higher latency/different URL (if not using global LB).
*   **Restore**: Deletes from `us-west1` and redeploys to `us-central1`.

---

## 🔧 Technical Implementation Details

### Docker Configuration
Managed via the main `docker-compose.yml` in `finopti-platform`:

```yaml
  monkey_agent:
    build: ../chaos-monkey-testing/monkey_agent
    environment:
      - ORCHESTRATOR_URL=http://apisix:9080/orchestrator/ask
    networks:
      - finopti-net

  monkey_ui:
    build: ../chaos-monkey-testing/monkey_ui
    ports:
      - "8080:80"
    networks:
      - finopti-net
```

### Cloud Run Agent "Subprocess" Fix
To bypass limitations of the MCP server protocol for complex gcloud commands, the agent uses Python's `subprocess`:

```python
# Copy config to writable location to fix Read-Only errors
shutil.copytree("/root/.config/gcloud", "/tmp/gcloud_config")

# Execute command
subprocess.run(
    ["gcloud", "run", "deploy", ...],
    env={"CLOUDSDK_CONFIG": "/tmp/gcloud_config"}
)
```

## 🧪 Verification
The setup has been verified by running the **Service Blackout** scenario:
1.  **Break**: UI clicked -> Service deleted on GCP.
2.  **Troubleshoot**: MATS agents detected the 404 and identified the deletion.
3.  **Restore**: UI clicked -> Service successfully redeployed and accessible.
