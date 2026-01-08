FROM python:3.11-slim

WORKDIR /app

# Install docker client for spawning capability
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    && curl -fsSL https://get.docker.com -o get-docker.sh \
    && sh get-docker.sh \
    && rm -rf /var/lib/apt/lists/*

COPY sub_agents/cloud_run_agent_adk/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sub_agents/cloud_run_agent_adk/ .
COPY sub_agents/cloud_run_agent_adk/agent.py .
COPY config/ config/

CMD ["python", "main.py"]
