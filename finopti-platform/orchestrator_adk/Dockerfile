FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY orchestrator_adk/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all Python files from orchestrator_adk
# Copy all Python files from orchestrator_adk
COPY orchestrator_adk/*.py .

# Copy Master Agent Registry
COPY orchestrator_adk/master_agent_registry.json .

# Copy config module
COPY config /app/config

# Copy shared common modules
COPY mats-agents/common/ /app/common/
COPY common/ /app/common/
RUN touch /app/common/__init__.py

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
  CMD curl -f http://localhost:5000/health || exit 1

# Run the Flask app
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "1800", "main:app"]
