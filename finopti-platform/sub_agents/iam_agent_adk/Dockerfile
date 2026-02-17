FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y docker.io procps curl && \
    rm -rf /var/lib/apt/lists/*

# Install python deps
COPY sub_agents/iam_agent_adk/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy config and common libs
COPY config/ config/
COPY common/ common/
# Specifically for IAM Agent
COPY sub_agents/iam_agent_adk/ .

# Env vars
ENV PYTHONUNBUFFERED=1

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--timeout", "600", "main:app"]
