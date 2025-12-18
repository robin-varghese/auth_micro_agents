#!/bin/bash

# APISIX Route Initialization Script
# This script configures all routes in APISIX via the Admin API

set -e

echo "Waiting for APISIX to be ready..."
sleep 10

APISIX_ADMIN="http://apisix:9180/apisix/admin"
ADMIN_KEY="finopti-admin-key"

echo "Initializing APISIX routes..."

# Route 1: Orchestrator
echo "Creating route: /orchestrator -> orchestrator:5000"
curl -i -X PUT "${APISIX_ADMIN}/routes/1" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "orchestrator_route",
    "uri": "/orchestrator/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "orchestrator:5000": 1
      },
      "timeout": {
        "connect": 6,
        "send": 60,
        "read": 60
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/orchestrator/(.*)", "/$1"]
      }
    }
  }'

echo ""

# Route 2: GCloud Agent
echo "Creating route: /agent/gcloud -> gcloud_agent:5001"
curl -i -X PUT "${APISIX_ADMIN}/routes/2" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "gcloud_agent_route",
    "uri": "/agent/gcloud/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "gcloud_agent:5001": 1
      },
      "timeout": {
        "connect": 6,
        "send": 60,
        "read": 60
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/agent/gcloud/(.*)", "/$1"]
      }
    }
  }'

echo ""

# Route 3: Monitoring Agent
echo "Creating route: /agent/monitoring -> monitoring_agent:5002"
curl -i -X PUT "${APISIX_ADMIN}/routes/3" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "monitoring_agent_route",
    "uri": "/agent/monitoring/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "monitoring_agent:5002": 1
      },
      "timeout": {
        "connect": 6,
        "send": 60,
        "read": 60
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/agent/monitoring/(.*)", "/$1"]
      }
    }
  }'

echo ""

# Route 4: GCloud MCP Server
echo "Creating route: /mcp/gcloud -> gcloud_mcp:6001"
curl -i -X PUT "${APISIX_ADMIN}/routes/4" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "gcloud_mcp_route",
    "uri": "/mcp/gcloud/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "gcloud_mcp:6001": 1
      },
      "timeout": {
        "connect": 6,
        "send": 60,
        "read": 60
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/mcp/gcloud/(.*)", "/$1"]
      }
    }
  }'

echo ""

# Route 5: Monitoring MCP Server
echo "Creating route: /mcp/monitoring -> monitoring_mcp:6002"
curl -i -X PUT "${APISIX_ADMIN}/routes/5" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "monitoring_mcp_route",
    "uri": "/mcp/monitoring/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "monitoring_mcp:6002": 1
      },
      "timeout": {
        "connect": 6,
        "send": 60,
        "read": 60
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/mcp/monitoring/(.*)", "/$1"]
      }
    }
  }'

echo ""
echo "All routes initialized successfully!"

# List all routes
echo ""
echo "Listing all configured routes:"
curl -s "${APISIX_ADMIN}/routes" -H "X-API-KEY: ${ADMIN_KEY}" | python3 -m json.tool || echo "Routes configured"

echo ""
echo "Route initialization complete!"
