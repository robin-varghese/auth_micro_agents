# MATS Evaluation - README

## Overview

This directory contains the testing and evaluation infrastructure for MATS (Micro Agent Troubleshooting System).

## Scripts

### 1. `deploy_mats_local.sh`
Deploys MATS services to local Docker Desktop.

**Usage:**
```bash
# Interactive mode - select services
./deploy_mats_local.sh

# Deploy all MATS services
./deploy_mats_local.sh a

# Deploy specific services
./deploy_mats_local.sh mats-orchestrator mats-sre-agent
```

**Services Deployed:**
- `mats-orchestrator` (Port 8080)
- `mats-sre-agent` (Port 8081)
- `mats-investigator-agent` (Port 8082)
- `mats-architect-agent` (Port 8083)

### 2. `reset_and_test_mats.sh`
Complete reset and test cycle for MATS.

**Usage:**
```bash
./reset_and_test_mats.sh
```

**What it does:**
1. **Clean-up**: Stops and removes all MATS containers and images
2. **Build**: Rebuilds MATS Docker images from scratch
3. **Deploy**: Starts all MATS services
4. **Health Check**: Waits for services to be healthy
5. **Test**: Runs the MATS test suite

### 3. `run_mats_tests.py`
Test suite for MATS functionality.

**Usage:**
```bash
python3 run_mats_tests.py
```

**Tests Performed:**
- ✅ Health checks for all 4 services
- ✅ Direct orchestrator troubleshoot endpoint
- ✅ APISIX route (if configured)
- ✅ Official verification script

**Example Output:**
```
✅ PASS: Health Check - Orchestrator
✅ PASS: Health Check - SRE Agent
✅ PASS: Direct Troubleshoot Request
Total: 6 | Passed: 6 | Failed: 0
```

## Quick Start

### First Time Setup
```bash
# 1. Ensure Docker Desktop is running
# 2. Authenticate with GCP
gcloud auth application-default login

# 3. Navigate to project root
cd finopti-platform

# 4. Run reset and test
./mats-eval/reset_and_test_mats.sh
```

### Development Workflow

**Deploy changes:**
```bash
cd mats-eval
./deploy_mats_local.sh
```

**Run tests only:**
```bash
cd mats-eval
python3 run_mats_tests.py
```

**Full reset:**
```bash
cd mats-eval
./reset_and_test_mats.sh
```

## Test Scenarios

### Health Checks (4 tests)
- Orchestrator: `http://localhost:8080/health`
- SRE Agent: `http://localhost:8081/health`
- Investigator Agent: `http://localhost:8082/health`
- Architect Agent: `http://localhost:8083/health`

### Functional Tests (2 tests)
1. **Direct Troubleshoot**
   - Endpoint: `POST http://localhost:8080/troubleshoot`
   - Payload:
     ```json
     {
       "user_request": "Test troubleshooting request",
       "project_id": "test-project",
       "repo_url": "https://github.com/test/repo"
     }
     ```
   - Expected: `status` and `session_id` fields

2. **APISIX Route** (optional)
   - Endpoint: `POST http://localhost:9080/mats/orchestrator/troubleshoot`
   - Same payload as above

## Troubleshooting

### Services won't start
```bash
# Check logs
docker logs mats-orchestrator
docker logs mats-sre-agent

# Check if ports are in use
lsof -i :8080
lsof -i :8081

# Force clean
docker-compose down -v
docker system prune -f
```

### Tests failing
```bash
# Verify services are healthy
curl http://localhost:8080/health
curl http://localhost:8081/health

# Check service status
docker-compose ps mats-orchestrator mats-sre-agent

# View recent logs
docker logs mats-orchestrator | tail -50
```

### Orchestrator health check timeout
```bash
# Check if image was built
docker images | grep mats-orchestrator

# Rebuild
docker-compose build mats-orchestrator
docker-compose up -d mats-orchestrator

# Watch logs
docker logs -f mats-orchestrator
```

## Directory Structure

```
mats-eval/
├── deploy_mats_local.sh       # Deployment script
├── reset_and_test_mats.sh     # Reset & test script
├── run_mats_tests.py           # Test runner
├── README.md                   # This file
├── ground_truth.yaml           # (Optional) For future eval harness
└── eval_harness.py             # (Optional) For future scenario evaluation
```

## Environment Variables

Set these in your environment or docker-compose.yml:

```bash
MATS_ORCHESTRATOR_URL=http://localhost:8080
APISIX_URL=http://localhost:9080
GCP_PROJECT_ID=your-project-id
GOOGLE_API_KEY=your-api-key
GITHUB_PERSONAL_ACCESS_TOKEN=your-token
MATS_RCA_BUCKET=mats-rca-reports
```

## CI/CD Integration

Add to your CI pipeline:

```yaml
- name: Test MATS
  run: |
    cd finopti-platform/mats-eval
    ./reset_and_test_mats.sh
```

## Future Enhancements

- [ ] Scenario-based evaluation using `eval_harness.py`
- [ ] Integration with chaos monkey for fault injection
- [ ] Performance benchmarking (latency, throughput)
- [ ] Multi-scenario ground truth validation
- [ ] Automated RCA quality scoring

## Related Documentation

- [MATS Implementation Guide](../mats-agents/mats-docs/MATS_IMPLEMENTATION_COMPLETE.md)
- [API Documentation](../mats-agents/mats-docs/MATS_API_DOCUMENTATION.md)
- [Docker Compose Integration](../mats-agents/mats-docs/DOCKER_COMPOSE_INTEGRATION.md)
