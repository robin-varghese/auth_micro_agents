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
    *   **Simulate 🔴**: Triggers the `break_prompt`.
    *   **Restore 🟢**: Triggers the `restore_prompt`.
    *   **Live Logs 📜** (New): Dedicated tab to stream Cloud Run logs.

#### 🧠 Monkey Agent (Backend)
*   **Tech Stack**: Python (Flask).
*   **Location**: `auth_micro_agents/chaos-monkey-testing/monkey_agent/`
*   **Port**: 5007
*   **Endpoints**:
    *   `GET /scenarios`: Returns list of available chaos scenarios.
    *   `POST /execute`: Accepts `{id, action}` and forwards the prompt to the Orchestrator.
    *   `GET /logs`: Proxies request to Orchestrator -> Monitoring Agent to fetch recent logs.

#### 🌩️ Cloud Run Agent (The Executor)
*   **Tech Stack**: Python (Google ADK) + `gcloud` subprocess.
*   **Location**: `auth_micro_agents/finopti-platform/sub_agents/cloud_run_agent_adk/`
*   **Execution Model**: Direct `gcloud` execution for reliability.

#### 🔍 Monitoring Agent (The Observer)
*   **Tech Stack**: Python (Google ADK) + `gcloud` subprocess.
*   **Location**: `auth_micro_agents/finopti-platform/sub_agents/monitoring_agent_adk/`
*   **Responsibility**: Fetching metrics and logs. 
*   **Refactor Needed**: Switch from `MonitoringMCPClient` to direct `gcloud logging read` to ensure stability for the Live Logs feature.

### 2. Communication Flow (Chaos)
1.  **User** clicks "Simulate" on Monkey UI.
2.  **Monkey Agent** sends prompt to **Orchestrator**.
3.  **Orchestrator** routes to **Cloud Run Agent**.
4.  **Cloud Run Agent** executes `gcloud run` command.

### 3. Communication Flow (Live Logs)
1.  **Monkey UI** polls `GET /logs?service=calculator-app` every 5 seconds.
2.  **Monkey Agent** sends prompt to **Orchestrator**: *"Fetch last 20 lines of logs for Cloud Run service 'calculator-app' in desc order."*
3.  **Orchestrator** routes to **Monitoring Agent**.
4.  **Monitoring Agent** executes `gcloud logging read ...` via subprocess.
5.  **Result** (JSON logs) returned to UI.

---

## 💥 Implemented Chaos Scenarios

The following 10 scenarios are defined in `monkey_agent/scenarios.py` and actively running.

### 1. Service Blackout (Total Destruction)
*   **Action**: `gcloud run services delete calculator-app ...`
*   **Restore**: Redeploys the service using the Artifact Registry image.

### 2. Auth Lockdown (Permission Denied)
*   **Action**: Removes `roles/run.invoker` from `allUsers`.
*   **Restore**: Re-grants `roles/run.invoker` to `allUsers`.

### 3. Broken Deployment (CrashLoopBackOff)
*   **Action**: Deploys `gcr.io/google-containers/pause:1.0`.
*   **Restore**: Redeploys the correct `calculator-app` image.

### 4. Traffic Void (Misrouting)
*   **Action**: Sets traffic to 0%.
*   **Restore**: Routes 100% traffic to `LATEST`.

### 5. Resource Starvation (OOM Kill)
*   **Action**: Sets memory limit to `64Mi`.
*   **Restore**: Sets memory limit back to `512Mi`.

### 6. Concurrency Freeze (Latency Spike)
*   **Action**: Sets `concurrency=1` and `max-instances=1`.
*   **Restore**: Resets concurrency to default (80).

### 7. Bad Environment (Config Failure)
*   **Action**: Injects `DB_CONNECTION_STRING=invalid_host:5432`.
*   **Restore**: Removes the invalid environment variable.

### 8. Network Isolation (Ingress Restriction)
*   **Action**: Sets ingress to `internal`.
*   **Restore**: Sets ingress to `all`.

### 9. Cold Start Freeze (Scale to Zero)
*   **Action**: Sets `min-instances=0` and `max-instances=0`.
*   **Restore**: Sets `min-instances=1`.

### 10. Region Failover (Disaster Recovery)
*   **Action**: Deletes from `us-central1` AND deploys to `us-west1`.
*   **Restore**: Deletes from `us-west1` and redeploys to `us-central1`.

---

## 🔧 Technical Implementation Details

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

### New: Live Logs Implementation Plan
1.  **Frontend**: Add "Live Logs" tab to `index.html` with polling JS.
2.  **Backend**: Add `GET /logs` endpoint to `monkey_agent/main.py`.
3.  **Monitoring Agent**: Refactor to use `subprocess` for `gcloud logging read` (Port fix from SRE Agent).
4.  **Orchestrator**: Ensure routing prompt handles "fetch logs" correctly.

## 🧪 Verification
The setup has been verified by running the **Service Blackout** scenario and verifying the **SRE Agent's** ability to query logs via subprocess.
