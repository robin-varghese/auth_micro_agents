FROM python:3.11-slim

WORKDIR /app

# Install docker CLI + gcloud CLI (Modern GPG)
RUN apt-get update && apt-get install -y docker.io procps curl gnupg && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    apt-get update && apt-get install -y google-cloud-cli && \
    rm -rf /var/lib/apt/lists/*

COPY mats-agents/sre_agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config/ config/
COPY mats-agents/sre_agent/ .

# Set unbuffered output for logs to appear in Loki
ENV PYTHONUNBUFFERED=1

CMD ["gunicorn", "--bind", "0.0.0.0:8081", "--timeout", "600", "main:app"]
