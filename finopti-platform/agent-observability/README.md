# FinOpti Platform - Agent Observability

Centralized observability stack for FinOpti agents using Arize Phoenix and OpenTelemetry.

## Components

- **Arize Phoenix**: LLM observability and tracing UI (port 6006)
- **PostgreSQL**: Database backend for Phoenix (port 5433)
- **Session Extractor Plugin**: Custom plugin to extract session IDs from spans

## Quick Start

```bash
# Start observability stack
docker-compose up -d

# Access Phoenix UI
open http://localhost:6006
```

## Session ID Tracking

The `session_extractor.py` plugin enables Phoenix to correctly group traces by session ID for multi-user tracking.

### How It Works

1. **Session ID Generation**: UI generates unique session ID on login
2. **Span Attributes**: Orchestrator sets `session.id` attribute on spans
3. **Phoenix Extraction**: Plugin extracts session ID from span attributes
4. **Session Grouping**: Phoenix groups all traces by session ID in UI

### Supported Attribute Names

The extractor checks for session IDs in this priority order:
- `session.id` (OpenInference standard - **recommended**)
- `session_id` (custom attribute)
- `openinference.session.id` (alternative format)
- Fallback: `trace_id` for root spans

## Configuration

Session extractor is automatically loaded via environment variable:

```yaml
environment:
  - PHOENIX_SESSION_EVALUATOR_FILE_PATH=/app/session_extractor.py
volumes:
  - ./session_extractor.py:/app/session_extractor.py:ro
```

## Troubleshooting

### Session IDs Not Appearing in Phoenix

1. **Check Plugin Mount**:
   ```bash
   docker exec finopti-phoenix-standalone ls -la /app/session_extractor.py
   ```

2. **Check Environment Variable**:
   ```bash
   docker exec finopti-phoenix-standalone env | grep PHOENIX_SESSION
   ```

3. **Restart Phoenix**:
   ```bash
   docker-compose restart phoenix
   ```

4. **Check Span Attributes**: In Phoenix UI, click on a trace and verify `session.id` attribute exists

## References

- [Arize Phoenix Documentation](https://docs.arize.com/phoenix)
- [OpenInference Semantic Conventions](https://github.com/Arize-ai/openinference/)
