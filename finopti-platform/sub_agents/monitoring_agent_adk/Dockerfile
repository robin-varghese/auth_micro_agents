FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
# Install system dependencies including gcloud
RUN apt-get update && apt-get install -y docker.io procps curl gnupg && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    apt-get update && apt-get install -y google-cloud-cli && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY sub_agents/monitoring_agent_adk/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all Python files
COPY sub_agents/monitoring_agent_adk/*.py .

# Copy common utils
COPY common /app/common

# Copy config
COPY config /app/config

# Expose port
EXPOSE 5002

# Health check
HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
  CMD curl -f http://localhost:5002/health || exit 1

# Run Flask app
CMD ["python", "main.py"]
