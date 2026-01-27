FROM python:3.11-slim

WORKDIR /app

# Install docker CLI + gcloud CLI (Modern GPG)
RUN apt-get update && apt-get install -y docker.io procps curl gnupg && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    apt-get update && apt-get install -y google-cloud-cli && \
    rm -rf /var/lib/apt/lists/*

# Copy orchestrator requirements first
COPY mats-agents/mats-orchestrator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared config directory
COPY config/ config/

# Copy all orchestrator code
COPY mats-agents/mats-orchestrator/ .

# Expose port
EXPOSE 8080

# Run Flask app
CMD ["python", "main.py"]
