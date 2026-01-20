# Strategy for Debugging and Fixing Sub-Agents

**Objective**: Fix the remaining failing agents (`db`, `filesystem`, `sequential`, `storage`) to achieve 100% verification pass rate (excluding `brave_search`).

## 1. General Observations
## 1. General Observations
**Latest Run Results (2026-01-20):**
*   **PASSED**: `analytics`, `cloud_run`, `code_execution`, `gcloud`, `github` (mostly), `google_search` (pending).
*   **FAILED**: 
| Agent | Status | Error Type | Observations |
| :--- | :--- | :--- | :--- |
| Agent | Status | Error Type | Observations |
| :--- | :--- | :--- | :--- |
| `filesystem_agent_adk` | **Passed** | N/A | Fixed by replacing manual subprocess code with `mcp` library. |
| `db_agent_adk` | **Passed** | N/A | Fixed by creating non-empty table to prevent infinite loop. |
| `sequential_thinking_agent_adk` | **Passed** | N/A | Fixed by replacing manual subprocess code with `mcp` library. |
| `storage_agent_adk` | **Passed** | N/A | Verified successfully without code changes. |
| `brave_search_agent_adk` | **Skipped** | Timeout | Skipped per user request. |

The `filesystem` interactive script **successfully connected** to the MCP server, confirming the Docker container and stdio transport *can* work. The issue likely lies in the `filesystem_agent_adk/agent.py` implementation or how it manages the subprocess.

---

## 2. Baseline Verification (Interactive Scripts)
Before fixing `agent.py`, we MUST verify the underlying MCP server works using the existing interactive CLI scripts.

**Pre-requisite:**
Ensure `GOOGLE_API_KEY` is set. You can fetch it directly from Secret Manager:
```bash
export GOOGLE_API_KEY=$(gcloud secrets versions access latest --secret="google-api-key" --project="vector-search-poc")
```

**Script Locations:**
*   **Filesystem**: `temp_mcp_repo/filesystem/filesystem_interactive.py`
*   **DB**: `temp_mcp_repo/gcloud-mcpserver/google-db-mcp-toolbox/db_mcp_interactive.py`
*   **Storage**: `temp_mcp_repo/gcloud-mcpserver/remote-mcp-server/google-storage-mcp/storage_mcp_interactive.py`
*   **Monitoring**: `temp_mcp_repo/gcloud-mcpserver/remote-mcp-server/gcloud-monitoring-mcp/monitoring_interactive.py`
*   **Sequential**: `temp_mcp_repo/sequentialthinking/sequentialthinking_interactive.py`

**Action**: Run these scripts. If they work, the issue is strictly in the Agent <-> MCP connection (agent.py). If they fail, the issue is in the MCP Server itself (Dockerfile/Code).

## 3. Agent-Specific Strategies

### A. Filesystem Agent (`filesystem_agent_adk`)
**Issue**: Test Suite fails with "Connection lost". Interactive script connects OK.
**Analysis**: 
The interactive script uses `mcp.ClientSession` over stdio directly. The ADK agent likely wraps this. 
If the ADK agent is running *inside* a container (in the test suite environment), it might be struggling to spawn the sibling MCP container due to Docker socket issues or path mapping.
**Debug Plan**:
1.  **Inspect `agent.py`**: Check how it launches the subprocess.
2.  **Verify Docker Socket**: Ensure the `filesystem_agent_adk` container has access to `docker.sock`.
3.  **Fix**: Unify the `agent.py` connection logic with the working interactive script logic.

### B. DB Agent (`db_agent_adk`)
**Issue**: Timeouts. `google-db-mcp-toolbox` is a complex image.
**Debug Plan**:
1.  **Check Auth**: The DB toolbox likely needs Google Cloud credentials. Even if `agent.py` has `GOOGLE_API_KEY`, the spawned container environment might be missing it.
    *   *Fix*: Ensure `docker run -e GOOGLE_API_KEY=...` is passed.
2.  **Check Startup Logs**: Manually run the MCP docker command causing the hang to see stderr output.

### C. Sequential Thinking Agent (`sequential_thinking_agent_adk`)
**Issue**: Timeouts.
**Debug Plan**:
1.  **Stdio Communication**: This is a Node.js based MCP server. Check if it requires any specific Environment Variables.
2.  **Buffering**: Ensure Python's `subprocess` interactions rely on `line` buffering and aren't waiting for a buffer to fill.

### D. Storage Agent (`storage_agent_adk`)
**Issue**: Timeouts. Similar to Filesystem.
**Debug Plan**:
1.  **Auth**: Like DB Agent, ensure GCP credentials propagate to the MCP container.

---

## 3. General "Standardization" Action Plan

For each agent, we will apply the **Code Execution Agent** pattern (which works):

1.  **Refactor `agent.py`**:
    *   Ensure `ServiceMCPClient` properly streams `stdin`/`stdout`.
    *   Add explicit logging for `docker run` command construction.
    *   Pass `GOOGLE_API_KEY` and `GCP_PROJECT_ID` into the MCP container if needed.
2.  **Docker Compose**:
    *   Ensure all agents have `docker.sock` if they need to spawn peers.
3.  **Verification**:
    *   Run `python3 tests/run_suite.py` after each fix.

## 4. Brave Search Agent
**Status**: **SKIPPED**.
**Reason**: Missing API Key.
**Action**: Comment out verification step or mark as "Expected Fail" in suite.

---

## 5. Execution Order
1.  **Filesystem** (Easiest to debug path issues).
2.  **Sequential** (Node.js stdio check).
3.  **Storage** (Auth check).
4.  **DB** (Complex auth checks).
