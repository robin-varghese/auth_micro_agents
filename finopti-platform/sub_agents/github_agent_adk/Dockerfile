FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including docker cli (for MCP spawning)
RUN apt-get update && apt-get install -y \
    curl \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY sub_agents/github_agent_adk/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Python files
COPY sub_agents/github_agent_adk/*.py .

# Copy common utils
COPY common /app/common

# Copy config
COPY config /app/config

# Structured logging
COPY orchestrator_adk/structured_logging.py /app/orchestrator/

EXPOSE 5003

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
  CMD curl -f http://localhost:5003/health || exit 1

CMD ["python", "main.py"]
