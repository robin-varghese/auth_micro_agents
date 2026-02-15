# Refactoring Strategy: All Sub-Agents

**Objective**: Standardize the 13 sub-agents in `finopti-platform/sub_agents` to use the modular architecture defined in Phase 12 (MATS Refactoring). This ensures maintainability, testability, and consistent observability.

## Agent Classification

### Category A: MCP Wrapper Agents
*These agents wrap an external Model Context Protocol (MCP) server (Docker/Stdio or HTTP).*

1.  **gcloud_agent_adk** (Docker Stdio)
2.  **github_agent_adk** (Docker Stdio)
3.  **monitoring_agent_adk** (Docker Stdio/HTTP)
4.  **db_agent_adk** (Docker Stdio)
5.  **storage_agent_adk** (Docker Stdio)
6.  **cloud_run_agent_adk** (Docker Stdio?)
7.  **analytics_agent_adk** (Docker Stdio)
8.  **filesystem_agent_adk** (Docker Stdio)
9.  **puppeteer_agent_adk** (Docker Stdio)
10. **sequential_thinking_agent_adk** (Docker Stdio)
11. **brave_search_agent_adk** (Docker Stdio?)

### Category B: Native Tool Agents
*These agents use Python libraries directly or internal logic.*

1.  **googlesearch_agent_adk** (Uses `google.adk.tools.google_search`)
2.  **code_execution_agent_adk** (Likely uses `exec` or internal sandbox)

---

## Target Architecture

### Module Structure (Category A: MCP Wrapper)
| File | Responsibility |
|------|----------------|
| `agent.py` | **Entry Point**: App definition, Runner logic, Model Fallback. (< 200 lines) |
| `mcp_client.py` | **Infrastructure**: `AsyncMCPClient` class, connection logic, handshake. |
| `tools.py` | **Interface**: Python functions that wrap `mcp_client.call_tool`. |
| `instructions.py`| **Prompts**: System instructions and agent description. |
| `context.py` | **State**: ContextVars for session/user/redis, `_report_progress`. |
| `observability.py` | **Tracing**: Phoenix/OTel registration. |

### Module Structure (Category B: Native Tool)
| File | Responsibility |
|------|----------------|
| `agent.py` | **Entry Point**: App definition, Runner logic. (< 150 lines) |
| `tools.py` | **Implementation**: Actual tool logic (e.g., `google_search` wrapper). |
| `instructions.py`| **Prompts**: System instructions. |
| `context.py` | **State**: ContextVars, `_report_progress`. |
| `observability.py` | **Tracing**: Phoenix/OTel registration. |

---

## Common Modules (To Be Reused)
To reduce duplication, we should ideally move common logic to `sub_agents/common` or `finopti-platform/common`.
*Current Approach*: We will duplicate `context.py` and `observability.py` into each agent's folder for now to maintain isolation, but keep them identical.

## Execution Batches

### Phase 13: Core Infrastructure Agents (Priority: High)
*Focus: These are used by MATS SRE/Investigator.*
1.  **gcloud_agent_adk**
2.  **github_agent_adk**
3.  **monitoring_agent_adk**

### Phase 14: Specialized Cloud Agents
1.  **cloud_run_agent_adk**
2.  **db_agent_adk**
3.  **storage_agent_adk**
4.  **analytics_agent_adk**

### Phase 15: Utility Agents
1.  **sequential_thinking_agent_adk**
2.  **filesystem_agent_adk**
3.  **puppeteer_agent_adk**
4.  **brave_search_agent_adk**

### Phase 16: Native Agents
1.  **googlesearch_agent_adk**
2.  **code_execution_agent_adk**

---

## Refactoring Checklist (Per Agent)
- [ ] Create `observability.py` (Standard copy).
- [ ] Create `context.py` (Standard copy + Agent Name/Icon customization).
- [ ] Create `instructions.py` (Extract from `agent.py`).
- [ ] Create `mcp_client.py` (Extract Client Class if exists).
- [ ] Create `tools.py` (Extract tool wrappers).
- [ ] Rewrite `agent.py` (Imports, Factory, Runner).
- [ ] **Verify**: Run `docker-compose build <agent>` and check startup logs.
