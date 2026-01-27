# implementation_plan.md

## Goal
Integrate Arize Phoenix for agentic observability into the MATS ecosystem, starting with the **MATS Orchestrator**. Deploy locally via Docker Compose using the existing PostgreSQL database.

## User Review Required
> [!IMPORTANT]
> This change introduces a new service (`phoenix`) that exposes ports `6006` (UI) and `4317` (GRPC). Ensure these ports are available.
> The Orchestrator image size will increase slightly due to new dependencies.

## Proposed Changes

### Infrastructure ([docker-compose.yml](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/docker-compose.yml))
#### [NEW] Directory: `finopti-platform/agent-observability/`
- Create directory to store observability artifacts and configuration.
- Save a copy of this `implementation_plan.md` and `task.md` to this directory.

#### [MODIFY] [docker-compose.yml](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/docker-compose.yml)
- Add `phoenix` service:
    - Image: `arize-phoenix`
    - Ports: 
        - `6006:6006` (UI)
        - `4317:4317` (OTLP GRPC)
    - Environment:
        - `PHOENIX_SQL_DATABASE_URL`: `postgresql://postgres:postgres@db_postgres:5432/postgres`
    - Depends on: `db_postgres`
- Update `orchestrator` service:
    - Add environment variables:
        - `PHOENIX_COLLECTOR_ENDPOINT`: `http://phoenix:6006/v1/traces`
        - `OTEL_EXPORTER_OTLP_ENDPOINT`: `http://phoenix:4317`

### Orchestrator Agent
#### [MODIFY] [requirements.txt](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/mats-agents/mats-orchestrator/requirements.txt)
- Add:
    - `arize-phoenix>=4.0.0`
    - `opentelemetry-sdk`
    - `opentelemetry-exporter-otlp`
    - `openinference-instrumentation-google-genai` (if available, else generic `opentelemetry-instrumentation`)

#### [MODIFY] [agent.py](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/mats-agents/mats-orchestrator/agent.py)
- Import `phoenix.otel` and `opentelemetry`.
- Configure `PhoenixInstrumentor` or OTel Provider in `__main__` or setup block.
- Ensure traces are exported to the Phoenix service.

## Verification Plan

### Automated Verification
1. Rebuild images: `docker-compose build orchestrator phoenix`.
2. Start stack: `docker-compose up -d phoenix orchestrator`.
3. Verify Phoenix UI at `http://localhost:6006`.
4. Run a troubleshooting request via `curl`.
5. Check Phoenix UI for traces showing the request flow.

### Manual Verification
- Browse `http://localhost:6006` to confirm traces appear.
