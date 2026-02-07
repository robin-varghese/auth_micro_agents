FROM python:3.11-slim

WORKDIR /app

# Install docker CLI for spawning MCP containers
RUN apt-get update && apt-get install -y docker.io procps && rm -rf /var/lib/apt/lists/*

COPY mats-agents/mats-investigator-agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config/ config/
COPY mats-agents/common/ common/
COPY mats-agents/mats-investigator-agent/ .

ENV PYTHONUNBUFFERED=1

CMD ["gunicorn", "--bind", "0.0.0.0:8082", "--timeout", "600", "main:app"]
