FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# Install Python dependencies
COPY sub_agents/googlesearch_agent_adk/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY sub_agents/googlesearch_agent_adk/*.py .
COPY config /app/config

# Expose port
EXPOSE 5011

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:5011/health || exit 1

# Run the application
CMD ["python", "main.py"]
