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
COPY orchestrator_adk/structured_logging.py /app/orchestrator_adk/

EXPOSE 5005

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
  CMD curl -f http://localhost:5005/health || exit 1

CMD ["python", "main.py"]
