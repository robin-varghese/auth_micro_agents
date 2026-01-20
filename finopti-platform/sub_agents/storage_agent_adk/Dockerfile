FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including docker cli
RUN apt-get update && apt-get install -y \
    curl \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY sub_agents/storage_agent_adk/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Python files
COPY sub_agents/storage_agent_adk/*.py .

# Copy config
COPY config /app/config

# Structured logging
COPY orchestrator_adk/structured_logging.py /app/orchestrator/

EXPOSE 5004

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
  CMD curl -f http://localhost:5004/health || exit 1

CMD ["python", "main.py"]
