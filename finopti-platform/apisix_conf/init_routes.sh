#!/bin/bash

# APISIX Route Initialization Script
# This script configures all routes in APISIX via the Admin API

set -e

echo "Waiting for APISIX to be ready..."
sleep 10

APISIX_ADMIN=${APISIX_ADMIN:-"http://apisix:9180/apisix/admin"}
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
        "connect": 10,
        "send": 1800,
        "read": 1800
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
        "send": 600,
        "read": 600
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
        "send": 120,
        "read": 120
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
        "send": 120,
        "read": 120
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
        "send": 120,
        "read": 120
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/mcp/monitoring/(.*)", "/$1"]
      }
    }
  }'

echo ""

# Route 6: GitHub Agent
echo "Creating route: /agent/github -> github_agent:5003"
curl -i -X PUT "${APISIX_ADMIN}/routes/6" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "github_agent_route",
    "uri": "/agent/github/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "github_agent:5003": 1
      },
      "timeout": {
        "connect": 6,
        "send": 120,
        "read": 120
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/agent/github/(.*)", "/$1"]
      }
    }
  }'

echo ""

# Route 7: Storage Agent
echo "Creating route: /agent/storage -> storage_agent:5004"
curl -i -X PUT "${APISIX_ADMIN}/routes/7" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "storage_agent_route",
    "uri": "/agent/storage/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "storage_agent:5004": 1
      },
      "timeout": {
        "connect": 6,
        "send": 120,
        "read": 120
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/agent/storage/(.*)", "/$1"]
      }
    }
  }'

echo ""

# Route 8: Database Agent
echo "Creating route: /agent/db -> db_agent:5005"
curl -i -X PUT "${APISIX_ADMIN}/routes/8" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "db_agent_route",
    "uri": "/agent/db/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "db_agent:5005": 1
      },
      "timeout": {
        "connect": 6,
        "send": 120,
        "read": 120
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/agent/db/(.*)", "/$1"]
      }
    }
  }
'

echo ""

# Route 9: GitHub MCP Server
echo "Creating route: /mcp/github -> github_mcp:6003"
curl -i -X PUT "${APISIX_ADMIN}/routes/9" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "github_mcp_route",
    "uri": "/mcp/github/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "github_mcp:6003": 1
      },
      "timeout": {
        "connect": 6,
        "send": 120,
        "read": 120
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/mcp/github/(.*)", "/$1"]
      }
    }
  }'

echo ""

# Route 10: Storage MCP Server
echo "Creating route: /mcp/storage -> storage_mcp:6004"
curl -i -X PUT "${APISIX_ADMIN}/routes/10" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "storage_mcp_route",
    "uri": "/mcp/storage/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "storage_mcp:6004": 1
      },
      "timeout": {
        "connect": 6,
        "send": 120,
        "read": 120
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/mcp/storage/(.*)", "/$1"]
      }
    }
  }'

echo ""

# Route 11: Database MCP Server
echo "Creating route: /mcp/db -> db_mcp_toolbox:5000"
curl -i -X PUT "${APISIX_ADMIN}/routes/11" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "db_mcp_route",
    "uri": "/mcp/db/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "db_mcp_toolbox:5000": 1
      },
      "timeout": {
        "connect": 6,
        "send": 120,
        "read": 120
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/mcp/db/(.*)", "/$1"]
      }
    }
  }'

echo ""
# Route 12: Cloud Run Agent
echo "Creating route: /agent/cloud_run -> cloud_run_agent:5006"
curl -i -X PUT "${APISIX_ADMIN}/routes/12" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "cloud_run_agent_route",
    "uri": "/agent/cloud_run/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "cloud_run_agent:5006": 1
      },
      "timeout": {
        "connect": 6,
        "send": 600,
        "read": 600
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/agent/cloud_run/(.*)", "/$1"]
      }
    }
  }'

echo ""

# Route 13: Cloud Run MCP Server
echo "Creating route: /mcp/cloud-run -> cloud_run_mcp:6006"
curl -i -X PUT "${APISIX_ADMIN}/routes/13" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "cloud_run_mcp_route",
    "uri": "/mcp/cloud-run/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "cloud_run_mcp:6006": 1
      },
      "timeout": {
        "connect": 6,
        "send": 120,
        "read": 120
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/mcp/cloud-run/(.*)", "/$1"]
      }
    }
  }'

echo ""
# Route 14: MATS Orchestrator
echo "Creating route: /agent/mats -> mats-orchestrator:8084"
curl -i -X PUT "${APISIX_ADMIN}/routes/14" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "mats_orchestrator_route",
    "uri": "/agent/mats/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "mats-orchestrator:8084": 1
      },
      "timeout": {
        "connect": 10,
        "send": 1800,
        "read": 1800
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/agent/mats/(.*)", "/$1"]
      }
    }
  }'

echo ""

# Route 15: Brave Search Agent
echo "Creating route: /agent/brave -> brave_agent_adk:5006"
curl -i -X PUT "${APISIX_ADMIN}/routes/15" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "brave_agent_route",
    "uri": "/agent/brave/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "brave_agent_adk:5006": 1
      },
      "timeout": {
        "connect": 6,
        "send": 600,
        "read": 600
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/agent/brave/(.*)", "/$1"]
      }
    }
  }'

echo ""

# Route 16: Filesystem Agent
echo "Creating route: /agent/filesystem -> filesystem_agent_adk:5007"
curl -i -X PUT "${APISIX_ADMIN}/routes/16" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "filesystem_agent_route",
    "uri": "/agent/filesystem/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "filesystem_agent_adk:5007": 1
      },
      "timeout": {
        "connect": 6,
        "send": 600,
        "read": 600
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/agent/filesystem/(.*)", "/$1"]
      }
    }
  }'

echo ""

# Route 17: Analytics Agent
echo "Creating route: /agent/analytics -> analytics_agent_adk:5008"
curl -i -X PUT "${APISIX_ADMIN}/routes/17" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "analytics_agent_route",
    "uri": "/agent/analytics/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "analytics_agent_adk:5008": 1
      },
      "timeout": {
        "connect": 6,
        "send": 600,
        "read": 600
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/agent/analytics/(.*)", "/$1"]
      }
    }
  }'

echo ""

# Route 18: Puppeteer Agent
echo "Creating route: /agent/puppeteer -> puppeteer_agent_adk:5009"
curl -i -X PUT "${APISIX_ADMIN}/routes/18" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "puppeteer_agent_route",
    "uri": "/agent/puppeteer/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "puppeteer_agent_adk:5009": 1
      },
      "timeout": {
        "connect": 6,
        "send": 600,
        "read": 600
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/agent/puppeteer/(.*)", "/$1"]
      }
    }
  }'

echo ""

# Route 19: Sequential Thinking Agent
echo "Creating route: /agent/sequential -> sequential_thinking_agent_adk:5010"
curl -i -X PUT "${APISIX_ADMIN}/routes/19" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "sequential_agent_route",
    "uri": "/agent/sequential/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "sequential_thinking_agent_adk:5010": 1
      },
      "timeout": {
        "connect": 6,
        "send": 600,
        "read": 600
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/agent/sequential/(.*)", "/$1"]
      }
    }
  }'

echo ""

# Route 20: Google Search Agent
echo "Creating route: /agent/googlesearch -> googlesearch_agent_adk:5011"
curl -i -X PUT "${APISIX_ADMIN}/routes/20" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "googlesearch_agent_route",
    "uri": "/agent/googlesearch/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "googlesearch_agent_adk:5011": 1
      },
      "timeout": {
        "connect": 6,
        "send": 600,
        "read": 600
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/agent/googlesearch/(.*)", "/$1"]
      }
    }
  }'

echo ""

# Route 21: Code Execution Agent
echo "Creating route: /agent/code -> code_execution_agent_adk:5012"
curl -i -X PUT "${APISIX_ADMIN}/routes/21" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "code_agent_route",
    "uri": "/agent/code_execution/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "code_execution_agent_adk:5012": 1
      },
      "timeout": {
        "connect": 6,
        "send": 600,
        "read": 600
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/agent/code_execution/(.*)", "/$1"]
      }
    }
  }'

echo ""
# Route 22: Remediation Agent
echo "Creating route: /agent/remediation -> finopti-remediation-agent:8085"
curl -i -X PUT "${APISIX_ADMIN}/routes/22" \
  -H "X-API-KEY: ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "remediation_agent_route",
    "uri": "/agent/remediation/*",
    "upstream": {
      "type": "roundrobin",
      "nodes": {
        "finopti-remediation-agent:8085": 1
      },
      "timeout": {
        "connect": 6,
        "send": 600,
        "read": 600
      }
    },
    "plugins": {
      "proxy-rewrite": {
        "regex_uri": ["^/agent/remediation/(.*)", "/$1"]
      }
    }
  }'

echo ""
echo "All routes initialized successfully!"

# List all routes
echo ""
echo "Listing all configured configured routes:"
curl -s "${APISIX_ADMIN}/routes" -H "X-API-KEY: ${ADMIN_KEY}" | python3 -m json.tool || echo "Routes configured"

echo ""
echo "Route initialization complete!"
