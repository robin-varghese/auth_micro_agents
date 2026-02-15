FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y docker.io procps curl && \
    rm -rf /var/lib/apt/lists/*

# Install python deps
COPY mats-agents/mats-remediation-agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy common utils
COPY mats-agents/common/ common/
# Manual Injection: Copy CONTENT of google_adk_lib to .../google/adk/
COPY mats-agents/common/google_adk_lib/ /usr/local/lib/python3.11/site-packages/google/adk/

# HACK: Spoof google-adk metadata for openinference check
RUN mkdir -p /usr/local/lib/python3.11/site-packages/google_adk-1.24.1.dist-info && \
    echo "Metadata-Version: 2.1\nName: google-adk\nVersion: 1.24.1\n" > /usr/local/lib/python3.11/site-packages/google_adk-1.24.1.dist-info/METADATA

# If common is at root as well (repo structure varies), copy safeguards
# COPY common/ common/ 

COPY mats-agents/mats-remediation-agent/ .

# Env vars
ENV PYTHONUNBUFFERED=1
ENV PORT=8085

# CMD ["sleep", "infinity"]
CMD ["gunicorn", "--bind", "0.0.0.0:8085", "--timeout", "600", "main:app"]
