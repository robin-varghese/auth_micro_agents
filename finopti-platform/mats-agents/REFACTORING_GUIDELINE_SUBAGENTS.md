# Refactoring Guideline: MATS Sub-Agents (SRE, Investigator, Architect)

**Objective**: Decompose the monolithic `agent.py` in SRE, Investigator, and Architect agents into focused modules, ensuring consistency with the MATS Orchestrator architecture.

## Target Structure (Per Agent)

Each agent directory (`mats-sre-agent`, `mats-investigator-agent`, `mats-architect-agent`) should have:

1.  **`agent.py`**: Entry point (`process_request`, `create_app`). Reduced to high-level flow.
2.  **`tools.py`**: Tool definitions and implementations (e.g., `read_logs`, `read_file`).
3.  **`instructions.py`**: System prompts and described by variables.
4.  **`context.py`**: ContextVars (`session_id`, `user_email`) and `_report_progress` logic.
5.  **`observability.py`**: Phoenix/OTel registration.
6.  **`mcp_client.py`** (Investigator Only): `AsyncMCPClient` and GitHub client logic.

## Refactoring Steps (Repeat for Each Agent)

### 1. Extract `observability.py`
- **Source**: `agent.py` (lines ~30-55)
- **Functions**: `setup_observability()` (wrapper around `register` and `instrument`).
- **Imports**: `phoenix.otel`, `openinference`, `os`.

### 2. Extract `context.py`
- **Source**: `agent.py` (lines ~100-170)
- **Variables**: `_redis_publisher_ctx`, `_session_id_ctx`, `_user_email_ctx`.
- **Functions**: `_report_progress()`.
- **Imports**: `ContextVar`, `RedisEventPublisher`, `requests`, `logging`.

### 3. Extract `instructions.py`
- **Source**: `agent.py` (`create_agent` function's strings)
- **Variables**: `AGENT_DESCRIPTION`, `AGENT_INSTRUCTIONS`.
- **Note**: Decouple prompts from the `create_agent` function.

### 4. Extract `tools.py`
- **Source**: `agent.py` (Tool functions)
- **SRE**: `setup_gcloud_config`, `read_logs`.
- **Investigator**: `read_file`, `search_code`.
- **Architect**: `upload_rca_to_gcs`, `write_object`, `update_bucket_labels`.
- **Dependencies**: Uses `_report_progress` from `context.py`.

### 5. Extract `mcp_client.py` (Investigator Only)
- **Source**: `agent.py` (`AsyncMCPClient` class, `get_github_client`).
- **Dependencies**: `asyncio`, `json`, `logging`.

### 6. Rewrite `agent.py`
- **Imports**: Import everything from the new modules.
- **Factory**: `create_framework_agent` (using imported instructions/tools).
- **Runner**: `process_request` (keep logic, but use `context` module for vars).
- **Goal**: `< 200 lines`.

## Execution Order

1.  **MATS SRE Agent** (`mats-sre-agent`)
    -   Extract modules.
    -   Rewrite `agent.py`.
    -   Verify syntax.

2.  **MATS Investigator Agent** (`mats-investigator-agent`)
    -   Extract modules.
    -   Rewrite `agent.py`.
    -   Verify syntax.

3.  **MATS Architect Agent** (`mats-architect-agent`)
    -   Extract modules.
    -   Rewrite `agent.py`.
    -   Verify syntax.

4.  **Verification**
    -   Rebuild all 3 containers.
    -   Verify startup logs.
