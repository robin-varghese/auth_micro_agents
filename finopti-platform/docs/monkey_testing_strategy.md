# Chaos Monkey Testing Application Strategy

## 🎯 Objective
Develop a **Monkey Testing Web Application** to orchestrate controlled disruptions (chaos engineering) on the target Cloud Run service (`calculator-app`). 
The app will allow users to select from **10 distinct chaos scenarios**, execute them via an ADK-based agent, and revert the changes to restore service.

## 🏗️ Architecture Design

The solution will be integrated into the existing `finopti-platform` ecosystem, explicitly leveraging the **natively integrated MCP Servers** for direct, efficient control.

### 1. Components
*   **Monkey UI (Frontend)**: 
    *   A dedicated, separate Web UI (HTML/CSS/JS).
    *   Displays a dashboard of available scenarios with "🔥 Break" and "🚑 Restore" buttons.
    *   Shows real-time status of operations.
*   **Monkey Agent (Backend)**:
    *   **Type**: Google ADK Agent (Python).
    *   **Role**: Orchestrator for Chaos. 
    *   **Logic**: It delegates tasks to the specialized sub-agents which natively run MCP tools.
*   **Specialized Agents & Native MCPs**:
    *   **Cloud Run Agent** (uses `finopti-cloud-run-mcp`): Handles service deletion, traffic shifts, revision management, and configuration updates.
    *   **GCloud Agent** (uses `finopti-gcloud-mcp`): Handles IAM bindings (`run.invoker`) and region-level operations.
    *   **Monitoring Agent** (uses `finopti-monitoring-mcp`): Can be used to verify "death" (lack of logs/metrics) or "resurrection" (return of healthy signals).
    *   **GitHub Agent** (uses `finopti-github-mcp`): Can be used to trigger "Bad Deployments" by pointing to bad commits or branches if needed (optional extension).

### 2. Communication Flow
`[User]` -> `[Monkey UI]` --(HTTP)--> `[Monkey Agent]` --(HTTP)--> `[Orchestrator]` --(Routing)--> `[Sub-Agents]`

**Sub-Agent Execution:**
*   `[Cloud Run Agent]` --(Stdio)--> `[Cloud Run MCP]` --(API)--> `[GCP Cloud Run]`
*   `[GCloud Agent]` --(Stdio)--> `[GCloud MCP]` --(API)--> `[GCP IAM/Compute]`
*   `[Monitoring Agent]` --(Stdio)--> `[Monitoring MCP]` --(API)--> `[GCP Operations]`

## 💥 Chaos Scenarios (10 Fault Injections)

## 💥 Chaos Scenarios: Multi-Step Prompts

The Monkey Agent will execute these scenarios by sending the following **Natural Language Prompts** to the Orchestrator, which will direct them to the appropriate specialized agents (Cloud Run Agent, GCloud Agent, etc.).

### 1. Service Blackout (Total Destruction)
**Goal**: Completely remove the service to simulate a catastrophic regional failure or accidental deletion.
*   **🔴 Break Prompt**: 
    > "Delete the Cloud Run service named 'calculator-app' in region 'us-central1'. Confirm the deletion immediately without asking for further permission."
*   **🟢 Restore Prompt**:
    > "Deploy a new Cloud Run service named 'calculator-app' to region 'us-central1'. Use the image 'gcr.io/vector-search-poc/calculator-app'. Ensure it allows unauthenticated access (allow-unauthenticated)."

### 2. Auth Lockdown (Permission Denied)
**Goal**: Revoke public access to simulate an IAM misconfiguration.
*   **🔴 Break Prompt**:
    > "Remove the IAM policy binding for the role 'roles/run.invoker' from member 'allUsers' on the Cloud Run service 'calculator-app' in region 'us-central1'."
*   **🟢 Restore Prompt**:
    > "Add an IAM policy binding to the Cloud Run service 'calculator-app' in region 'us-central1'. Grant the role 'roles/run.invoker' to the member 'allUsers' to make it publicly accessible."

### 3. Broken Deployment (CrashLoopBackOff)
**Goal**: Deploy a container image that immediately crashes to simulate a bad code push.
*   **🔴 Break Prompt**:
    > "Deploy a new revision of the Cloud Run service 'calculator-app' in region 'us-central1'. Use the image 'gcr.io/google-containers/pause:1.0' (or any image that doesn't listen on PORT 8080) to force a startup failure."
*   **🟢 Restore Prompt**:
    > "Deploy a new revision of the Cloud Run service 'calculator-app' in region 'us-central1' using the known good image 'gcr.io/vector-search-poc/calculator-app'. Ensure 100% of traffic is routed to this new healthy revision."

### 4. Traffic Void (Misrouting)
**Goal**: Set traffic splitting configuration to drop traffic or route to a dummy "maintenance" mode.
*   **🔴 Break Prompt**:
    > "Update the traffic configuration for Cloud Run service 'calculator-app' in 'us-central1'. Set traffic to 0% for the latest revision, effectively stopping all requests." (Note: If 0% isn't allowed, route 100% to a non-functional revision).
*   **🟢 Restore Prompt**:
    > "Update the traffic configuration for Cloud Run service 'calculator-app' in 'us-central1'. Send 100% of traffic to the 'LATEST' revision."

### 5. Resource Starvation (OOM Kill)
**Goal**: Reduce memory to a point where the app crashes under load.
*   **🔴 Break Prompt**:
    > "Update the Cloud Run service 'calculator-app' in region 'us-central1'. Set the memory limit to '64Mi' (minimum possible)."
*   **🟢 Restore Prompt**:
    > "Update the Cloud Run service 'calculator-app' in region 'us-central1'. Set the memory limit back to '512Mi' (or previous working value)."

### 6. Concurrency Freeze (Latency Spike)
**Goal**: Artificially limit concurrency to force queuing and timeouts.
*   **🔴 Break Prompt**:
    > "Update the Cloud Run service 'calculator-app' in region 'us-central1'. Set the maximum concurrency per instance to 1 and set max-instances to 1."
*   **🟢 Restore Prompt**:
    > "Update the Cloud Run service 'calculator-app' in region 'us-central1'. Set concurrency to default (80) and remove the max-instances limit (or set to 100)."

### 7. Bad Environment (Config Failure)
**Goal**: Inject invalid environment variables that break application logic or connectivity.
*   **🔴 Break Prompt**:
    > "Update the Cloud Run service 'calculator-app' in 'us-central1'. Set the environment variable 'DB_CONNECTION_STRING' to 'invalid_host:5432' to force database connection errors."
*   **🟢 Restore Prompt**:
    > "Update the Cloud Run service 'calculator-app' in 'us-central1'. Remove the environment variable 'DB_CONNECTION_STRING' (or set it back to the valid connection string if known)."

### 8. Network Isolation (Ingress Restriction)
**Goal**: Restrict ingress to "Internal" or "Load Balancing" only, blocking public internet access.
*   **🔴 Break Prompt**:
    > "Update the Cloud Run service 'calculator-app' in 'us-central1'. Set the ingress traffic settings to 'internal'. This should block external HTTP traffic."
*   **🟢 Restore Prompt**:
    > "Update the Cloud Run service 'calculator-app' in 'us-central1'. Set the ingress traffic settings to 'all' to allow public internet access."

### 9. Cold Start Freeze (Scale to Zero)
**Goal**: Force aggressive scaling to zero and limit scaling up, causing cold starts for every request (or denial of service if clamped at 0).
*   **🔴 Break Prompt**:
    > "Update the Cloud Run service 'calculator-app' in 'us-central1'. Set 'min-instances' to 0 and 'max-instances' to 0 (effectively suspending the service) OR set max-instances to 1 to force serialization."
*   **🟢 Restore Prompt**:
    > "Update the Cloud Run service 'calculator-app' in 'us-central1'. Set 'min-instances' to 1 (to keep it warm) and remove the 'max-instances' limit."

### 10. Region Failover (Disaster Recovery Simulation)
**Goal**: Simulate US-Central1 going down and failing over to US-West1.
*   **🔴 Break Prompt (Multi-Step)**:
    > "Step 1: Delete the Cloud Run service 'calculator-app' in 'us-central1'. Step 2: Immediately deploy the service 'calculator-app' to region 'us-west1' using image 'gcr.io/vector-search-poc/calculator-app'."
*   **🟢 Restore Prompt (Multi-Step)**:
    > "Step 1: Delete the Cloud Run service 'calculator-app' in 'us-west1'. Step 2: Redeploy the service 'calculator-app' to region 'us-central1' using image 'gcr.io/vector-search-poc/calculator-app'."

*Note: Scenario 1 ("Delete Service") is destructive. The Restore action assumes the image is still in Registry.*

## 🚀 Implementation Plan

### Phase 1: Monkey Agent (ADK) Setup
1.  Create `mats-chaos-monkey` directory.
2.  Scaffold a basic ADK agent (`main.py`, `agent.py`).
3.  Implement `POST /trigger_chaos` endpoint accepting `scenario_id` and `action` ('break' | 'restore').
4.  Implement the logic to map `scenario_id` to the prompts defined above.
5.  Implement the `http_client` to call `GCloud Agent`.

### Phase 2: Monkey UI
1.  Create a simple dashboard `monkey-ui/index.html`.
2.  List the 10 scenarios with status indicators.
3.  Implement buttons to call the Monkey Agent.

### Phase 3: Integration
1.  Add `monkey-agent` to `docker-compose.yml`.
2.  Add `monkey-ui` to `docker-compose.yml` (or bundle with agent).
3.  Configure network routes in APISIX.

## ❓ Questions
1.  Do you want me to proceed with creating the `mats-chaos-monkey` folder now?
2.  Shall I use `docker-compose` to run this alongside the existing MATS stack?

---
**Ready to proceed?**
