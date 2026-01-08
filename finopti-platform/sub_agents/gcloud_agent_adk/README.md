# GCloud ADK Agent

Google Cloud infrastructure specialist built with Google ADK framework.

## Features

- **Google ADK Integration**: Uses Google's Agent Development Kit for intelligent GCP management
- **MCP Server Integration**: Connects to gcloud MCP server via Docker stdio
- **Natural Language Processing**: Understands requests in plain English
- **Structured Logging**: JSON logging with request ID tracing
- **HTTP API**: Flask-based REST API for easy integration

## Architecture

```
HTTP Request → Flask (main.py) → ADK Agent (agent.py) → MCP Client → GCloud MCP Server (Docker)
```

## API Endpoints

### POST /execute
Execute a GCloud operation

**Request Body**:
```json
{
  "prompt": "list all VMs",
  "user_email": "admin@example.com"
}
```

**Response**:
```json
{
  "success": true,
  "response": "Here are your VMs...",
  "agent": "gcloud_adk",
  "model": "gemini-3-pro-preview"
}
```

### GET /health
Health check endpoint

### GET /info
Get agent capabilities and configuration

## Environment Variables

See `.env.template` in project root.

Required:
- `GOOGLE_API_KEY` - Gemini API key
- `GCP_PROJECT_ID` - GCP project ID
- `GCLOUD_MCP_DOCKER_IMAGE` - MCP server Docker image

## Development

### Local Testing
```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python main.py
```

### Docker Build
```bash
docker build -t finopti-gcloud-agent-adk .
```

## Integration with Platform

This agent is called by the Orchestrator agent via APISIX:
```
APISIX → /agent/gcloud → GCloud ADK Agent → MCP Server
```

Authorization is handled by OPA before reaching this agent.
