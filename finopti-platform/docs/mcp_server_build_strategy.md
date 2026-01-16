# MCP Server Build & Deployment Strategy

This document outlines how to build and deploy the external MCP servers required for the FinOptiAgents Platform. These servers are hosted in the [robin-varghese/mcp-server](https://github.com/robin-varghese/mcp-server/) repository.

## 1. Prerequisites

- **Docker Desktop**: Installed and running.
- **Git**: To clone the repository.
- **Google Cloud SDK**: For authentication (`gcloud auth login`).
- **GitHub PAT**: For the GitHub MCP server.

## 2. Build Instructions

First, clone the repository:

```bash
git clone https://github.com/robin-varghese/mcp-server.git
cd mcp-server
```

### A. GCloud MCP Server (`finopti-gcloud-mcp`)
*Provides `gcloud` CLI capabilities.*

```bash
cd gcloud-mcpserver/remote-mcp-server/gcloud-mcp-server
docker build -t finopti-gcloud-mcp .
# Run manually to test:
# docker run -i --rm -v ~/.config/gcloud:/root/.config/gcloud finopti-gcloud-mcp
```

### B. Monitoring MCP Server (`finopti-monitoring-mcp`)
*Provides Cloud Monitoring metrics and logs.*

```bash
cd ../gcloud-monitoring-mcp
docker build -t finopti-monitoring-mcp .
```

### C. GitHub MCP Server (`finopti-github-mcp`)
*Provides GitHub repo search and file access.*

```bash
cd ../../../github-mcp-server
docker build -t finopti-github-mcp .
# Run manually to test (requires GITHUB_PERSONAL_ACCESS_TOKEN env var):
# docker run -i --rm -e GITHUB_PERSONAL_ACCESS_TOKEN=$GITHUB_TOKEN finopti-github-mcp
```

### D. Google Storage MCP (`finopti-storage-mcp`)
*Provides Cloud Storage bucket/object management.*

```bash
cd ../gcloud-mcpserver/remote-mcp-server/google-storage-mcp
docker build -t finopti-storage-mcp .
```

### E. Google Database Toolbox (`finopti-db-toolbox`)
*Provides PostgreSQL interactions.*

```bash
cd ../../google-db-mcp-toolbox
# This uses docker-compose
docker-compose up -d
```

### F. Google Analytics MCP (`finopti-analytics-mcp`)
*Provides GA4 reporting capabilities.*

```bash
cd ../remote-mcp-server/google-analytics-mcp
docker build -t finopti-analytics-mcp .
```

### G. Sequential Thinking MCP (`finopti-sequential-thinking`)
*Provides advanced reasoning capabilities.*

```bash
cd ../../../sequentialthinking
docker build -t finopti-sequential-thinking .
```

### H. Filesystem MCP (`finopti-filesystem`)
*Provides local file management.*

```bash
cd ../filesystem
docker build -t finopti-filesystem .
```

### I. Brave Search MCP (`finopti-brave-search`)
*Provides web and local search.*

```bash
cd ../brave-search
docker build -t finopti-brave-search .
```

### J. Puppeteer MCP (`finopti-puppeteer`)
*Provides browser automation.*

```bash
cd ../puppeteer
docker build -t finopti-puppeteer .
```

## 3. Integration with FinOpti Platform

Once built, these images are used by the main platform's `docker-compose.yml`. Ensure the image tags match what is expected in the main `docker-compose.yml` (e.g., `finopti-gcloud-mcp`).

## 4. Testing

Run the platform test suite to verify connectivity:

```bash
cd path/to/finopti-platform
python3 run_tests.py
```
