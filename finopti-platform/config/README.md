# Configuration Module - Secret Manager Integration

## Overview

This configuration module loads settings from **Google Secret Manager** (production) or `.env` file (local development).

## Features

- ✅ **Secret Manager Integration**: Loads from GCP Secret Manager in production
- ✅ **Local Development**: Falls back to `.env` file when available  
- ✅ **Project ID Resolution**: Auto-discovers project ID from credentials or resolves from project number
- ✅ **Comprehensive Validation**: Validates required configuration on startup
- ✅ **Smart Fallbacks**: Environment variables → Secret Manager → Defaults

## Usage

```python
from config import config

# Access configuration
api_key = config.GOOGLE_API_KEY
project_id = config.GOOGLE_PROJECT_ID
llm_model = config.FINOPTIAGENTS_LLM

# Or use module-level variables
from config import GOOGLE_API_KEY, GOOGLE_PROJECT_ID
```

## Configuration Modes

### Local Development (.env file)
```bash
# 1. Copy template
cp .env.template .env

# 2. Edit .env with your values
vim .env

# 3. Set mode to use .env
USE_SECRET_MANAGER=false
```

### Production (Secret Manager)
```bash
# Set environment variable or remove .env file
export USE_SECRET_MANAGER=true

# Or don't create .env file at all
# Config will automatically use Secret Manager
```

## Secret Naming Convention

Secrets in GCP Secret Manager must use **lowercase with hyphens**:

| Environment Variable | Secret Manager Name |
|---------------------|---------------------|
| `GOOGLE_API_KEY` | `google-api-key` |
| `FINOPTIAGENTS_LLM` | `finoptiagents-llm` |
| `BIGQUERY_DATASET_ID` | `bigquery-dataset-id` |

The config module automatically converts between formats.

## Creating Secrets in GCP

```bash
# Using gcloud CLI
gcloud secrets create google-api-key \
  --data-file=- <<< "your-api-key-value"

gcloud secrets create finoptiagents-llm \
  --data-file=- <<< "gemini-2.0-flash"

gcloud secrets create google-project-id \
  --data-file=- <<< "your-project-id"

# Grant access to service account
gcloud secrets add-iam-policy-binding google-api-key \
  --member="serviceAccount:your-sa@project.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

## Available Configuration

### Core Settings
- `GOOGLE_API_KEY` - Gemini API key
- `GOOGLE_PROJECT_ID` - GCP project ID
- `FINOPTIAGENTS_LLM` - LLM model name
- `GOOGLE_ZONE` - Default GCP zone

### Storage
- `STAGING_BUCKET_URI` - Staging bucket
- `PROD_BUCKET_URI` - Production bucket
- `PACKAGE_URI` - Package location

### BigQuery
- `BIGQUERY_DATASET_ID` - Dataset ID
- `BIGQUERY_TABLE_ID` - Table ID
- `BIGQUERYAGENTANALYTICSPLUGIN_TABLE_ID` - Analytics table

### RAG
- `RAG_Engine_LOCATION` - RAG engine location
- `RAG_EARB_DESIGNDOCS` - Design docs bucket

### Services
- `OPA_URL` - OPA service URL
- `APISIX_URL` - APISIX gateway URL
- `MONITORING_MCP_URL` - Monitoring MCP URL

## Error Handling

The module validates required configuration on import:

```python
# If GOOGLE_API_KEY or GOOGLE_PROJECT_ID is missing:
ValueError: FATAL: Could not determine Google Cloud Project ID...
```

Check logs for warnings about missing secrets:
```
WARNING - No value found for OPENAI_API_KEY
```

## Dependencies

Add to requirements.txt:
```
google-cloud-secret-manager>=2.16.0
google-cloud-resource-manager>=1.10.0
google-auth>=2.22.0
python-dotenv>=1.0.0
```
