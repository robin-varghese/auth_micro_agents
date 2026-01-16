FROM python:3.11-slim

WORKDIR /app

# Install docker client for spawning capability
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    && curl -fsSL https://get.docker.com -o get-docker.sh \
    && sh get-docker.sh \
    && rm -rf /var/lib/apt/lists/*

# Install Google Cloud SDK
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | \
    tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | \
    gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && \
    apt-get update && apt-get install -y google-cloud-cli

COPY sub_agents/cloud_run_agent_adk/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sub_agents/cloud_run_agent_adk/ .
COPY sub_agents/cloud_run_agent_adk/agent.py .
COPY config/ config/

EXPOSE 5006

# Health check
HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
  CMD curl -f http://localhost:5006/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5006", "--workers", "2", "--timeout", "600", "main:app"]
