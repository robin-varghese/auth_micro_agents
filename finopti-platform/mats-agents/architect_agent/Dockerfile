FROM python:3.11-slim

WORKDIR /app

# No docker CLI needed for Architect (pure reasoning), but keeping base consistent
RUN apt-get update && apt-get install -y procps && rm -rf /var/lib/apt/lists/*

COPY mats-agents/architect_agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config/ config/
COPY mats-agents/architect_agent/ .

ENV PYTHONUNBUFFERED=1

CMD ["gunicorn", "--bind", "0.0.0.0:8083", "main:app"]
