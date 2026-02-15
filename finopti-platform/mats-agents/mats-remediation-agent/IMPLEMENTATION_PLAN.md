# Implementation Plan - MATS Remediation Agent

## Goal Description
Create a new **Remediation Agent** (`mats-remediation-agent`) in the `mats-agents` directory.
This agent acts as the "closer" for the troubleshooting workflow. It takes an RCA document and the **Resolution** (from MATS Architect Agent) as input and autonomously:
1.  **Verifies** the current broken state (using Puppeteer).
2.  **Fixes** the issue (using GCloud/GitHub/Code Execution agents).
3.  **Validates** the fix (using Monitoring & Puppeteer).
4.  **Documents** the entire process in a PDF/Markdown report.
5.  **Uploads** the report to GCS (using Storage Agent) and returns the URL.

## User Review Required
> [!IMPORTANT]
> This agent has **write access** to infrastructure (GCloud) and code (GitHub).

## Critical Architecture
Adheres strictly to **AI_AGENT_DEVELOPMENT_GUIDE_V2.0.md** (Modular Architecture).

### Component Structure
```
mats-agents/mats-remediation-agent/
├── agent.py           # Wiring: App composition & State Machine
├── main.py            # Flask Entrypoint
├── context.py         # ContextVars & Redis Streaming
├── observability.py   # Phoenix Tracing
├── tools.py           # Delegation Tools (Puppeteer, GCloud, Monitoring, Storage)
├── instructions.py    # System Prompts
├── requirements.txt   # Dependencies
└── Dockerfile         # Container definition
```

## Proposed Changes

### [NEW] mats-agents/mats-remediation-agent

#### [NEW] [agent.py](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/mats-agents/mats-remediation-agent/agent.py)
- **Role**: State Machine orchestration.
- **Phases**: `PRE_VERIFY` -> `APPLY_FIX` -> `POST_VERIFY` -> `DOCUMENT`.
- **Logic**: 
  - Parses RCA to extract "Recommended Fix".
  - Calls `tools.run_puppeteer_test()` to confirm failure.
  - Calls `tools.apply_gcloud_fix()` or `tools.apply_github_fix()`.
  - Calls `tools.check_monitoring()` for error rate drop.
  - Generates report and calls `tools.upload_to_gcs()` (delegates to `storage-agent`).

#### [NEW] [tools.py](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/mats-agents/mats-remediation-agent/tools.py)
- **Pattern B** (Delegation to other agents via HTTP).
- **Functions**:
  - `delegate_to_puppeteer(url, scenario)`
  - `delegate_to_gcloud(command)`
  - `delegate_to_monitoring(query)`
  - `delegate_to_storage(content, filename)`

#### [NEW] [context.py](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/mats-agents/mats-remediation-agent/context.py)
- Standard boilerplate from V2.0 guide.

#### [NEW] [observability.py](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/mats-agents/mats-remediation-agent/observability.py)
- Standard boilerplate (`finoptiagents-MATS`).

#### [NEW] [main.py](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/mats-agents/mats-remediation-agent/main.py)
- Standard Flask entrypoint.

#### [NEW] [Dockerfile](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/mats-agents/mats-remediation-agent/Dockerfile)
- Standard Python 3.11 slim image.

### [MODIFY] docker-compose.yml
- Add `mats-remediation-agent` service definition.
- Expose on port `8085`.

## Verification Plan

### Automated Tests
1.  **Build Verification**: `docker-compose build mats-remediation-agent`
2.  **Startup Verification**: `docker-compose up -d mats-remediation-agent` -> Check logs for Phoenix connection.
3.  **API Verification**: `verify_agent.py` script to simulate a fix request.

### Manual Verification
1.  Trigger a "fix" for a known (safe) issue via generic prompt.
2.  Watch Redis stream for `PRE_VERIFY` -> `APPLY_FIX` steps.
3.  Check GCS bucket for the final report.
