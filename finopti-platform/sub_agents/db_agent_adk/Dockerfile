FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*
# Note: No docker CLI needed here since we use SSE network transport

# Copy requirements
COPY sub_agents/db_agent_adk/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Python files
COPY sub_agents/db_agent_adk/*.py .

# Copy config
COPY config /app/config

# Structured logging
COPY orchestrator/structured_logging.py /app/orchestrator/

EXPOSE 5005

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
  CMD curl -f http://localhost:5005/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5005", "--workers", "2", "--timeout", "120", "main:app"]
