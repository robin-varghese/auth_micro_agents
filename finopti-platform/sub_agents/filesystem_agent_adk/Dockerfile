FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY sub_agents/filesystem_agent_adk/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all Python files
COPY sub_agents/filesystem_agent_adk/*.py .

# Copy common utils
COPY common /app/common

# Copy config
COPY config /app/config

# Expose port
EXPOSE 5007

# Health check
HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
  CMD curl -f http://localhost:5007/health || exit 1

# Run Flask app
CMD ["gunicorn", "--bind", "0.0.0.0:5007", "--workers", "2", "--timeout", "120", "main:app"]
