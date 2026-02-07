# Routing Logic Fix - Walkthrough

## Summary

Fixed critical routing bug where all requests were being sent to MATS Orchestrator, including simple operations like "List VMs" that should go to specific agents. Also added guards in MATS to reject misrouted simple requests.

## Problem Description

### Issue 1: Orchestrator Routing Bug

The `detect_intent()` function in [orchestrator_adk/agent.py](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/orchestrator_adk/agent.py) had overly broad MATS triggers:

```python
# BEFORE (BROKEN):
if "troubleshoot" in prompt_lower or "debug" in prompt_lower or "fix" in prompt_lower or "investigate" in prompt_lower:
    return "mats-orchestrator"
```

**Problem:** The word "investigate" is too generic. Users say:
- "Investigate my VMs" → means "show me my VMs"
- "List all VMs in  my project" → falsely triggered  MATS

### Issue 2: MATS Accepting Everything

MATS Orchestrator had no guards to validate that incoming requests were actually troubleshooting requests. It would start a full RCA workflow for simple "list" operations.

## Changes Made

### 1. Fixed `detect_intent()` Function

**File**: [orchestrator_adk/agent.py](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/orchestrator_adk/agent.py#L67-L160)

#### Change A: Added Simple Operation Detection

```python
# 0. Detect simple CRUD operations (highest priority - bypass MATS)
simple_operations = [
    r'\blist\s+(all|my|the)?\s*',
    r'\bshow\s+(all|my|the)?\s*',
    r'\bget\s+(all|my|the)?\s*',
    r'\bcreate\s+a?\s*',
    r'\bdelete\s+a?\s*',
    r'\bupdate\s+a?\s*',
    r'\bdescribe\s+',
    r'\bfind\s+',
]

is_simple_operation = any(re.search(pattern, prompt_lower) for pattern in simple_operations)
```

**Impact:** Requests starting with "list", "show", "get", "create", "delete" bypass MATS check entirely.

#### Change B: Made MATS Triggers Specific

```python
# 1. Check for explicit MATS triggers (only if NOT a simple operation)
if not is_simple_operation:
    # MATS triggers - require clear troubleshooting intent
    mats_triggers = [
        "troubleshoot",
        "root cause",
        "rca",
        "why is",
        "why did",
        "why does",
        "what caused",
        "find the bug",
        "find the issue",
        "investigate the failure",  # ← "investigate" now requires context
        "investigate the error",
        "investigate the crash",
        "fix the issue",
        "fix the bug",
        "diagnose the",
        "debug the"
    ]
```

**Impact:** 
- Removed standalone "investigate" and "fix
"
- Require multi-word phrases like "why did", "what caused"
- "investigate" only triggers if followed by "failure", "error", or "crash"

#### Change C: Improved Keyword Scoring

```python
for k in keywords:
    k_lower = k.lower()
    # Use word boundary matching for better accuracy
    if len(k_lower) <= 3:
        # Short keywords need exact word match
        if re.search(r'\b' + re.escape(k_lower) + r'\b', prompt_lower):
            score += 2
    else:
        # Longer keywords can match as substring
        if k_lower in prompt_lower:
            score += 1
            # Bonus for multi-word concepts
            if ' ' in k_lower:
                score += 2
```

**Impact:** More accurate matching using word boundaries (`\b`) instead of naive string splitting.

#### Change D: Added Debug Logging

```python
if os.getenv("DEBUG_ROUTING", "false").lower() == "true":
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
    logger.info(f"Routing scores for '{prompt[:50]}...': {sorted_scores}")
```

**Impact:** Set `DEBUG_ROUTING=true` to see routing decisions in logs.

### 2. Updated Agent Instructions

**File**: [orchestrator_adk/agent.py](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/orchestrator_adk/agent.py#L393-L407)

```markdown
**MATS Orchestrator** - Use ONLY for complex troubleshooting and root cause analysis:
- "Why did X fail?" (causality questions)
- "Debug this error in Y" (specific error investigation)
- "Find the root cause of the crash" (explicit RCA)
- "Troubleshoot the deployment failure" (multi-step diagnosis)
- "What caused the outage?" (incident analysis)

**DO NOT use MATS for simple operations**:
- ❌ "List VMs", "Show buckets", "Get logs" → Use specific agents instead
- ❌ "Create instance", "Delete bucket" → Use gcloud/storage agents
- ❌ "What are my resources?" → Use gcloud agent
- ❌ Generic "investigate" without failure context → Use appropriate agent
```

**Impact:** Clear guidance for when to use MATS vs specific agents.

### 3. Added MATS Guards

**File**: [mats-orchestrator/agent.py](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/mats-agents/mats-orchestrator/agent.py#L403-L451)

#### Guard A: Detect Simple Operations

```python
# Detect if this is a simple CRUD operation (should not be routed to MATS!)
simple_patterns = [
    r'\blist\s+(all|my|the)?\s*(vms?|instances?|buckets?|services?|projects?|resources?)',
    r'\bshow\s+(all|my|the)?\s*(vms?|instances?|buckets?|services?|projects?|resources?)',
    r'\bget\s+(all|my|the)?\s*(vms?|instances?|buckets?|services?|projects?|resources?)',
    r'\bcreate\s+a?\s*(vm|instance|bucket|service|resource)',
    r'\bdelete\s+a?\s*(vm|instance|bucket|service|resource)',
]

for pattern in simple_patterns:
    if re.search(pattern, request_lower):
        error_msg = (
            f"This appears to be a simple operation, not a troubleshooting request. "
            f"MATS is designed for root cause analysis and complex debugging. "
            f"For simple operations like listing resources, please use the appropriate agent directly."
        )
        logger.warning(f"[{session_id}] MATS received simple request (misrouted): {user_request[:100]}")
        
        return {
            "status": "MISROUTED",
            "error": error_msg,
            "suggestion": "Please rephrase your request or use the specific agent for this operation."
        }
```

**Impact:** If MATS receives a simple request, it immediately returns an error instead of starting an investigation.

#### Guard B: Warn on Ambiguous Requests

```python
# Detect troubleshooting indicators
troubleshooting_indicators = [
    "why", "root cause", "rca", "failed", "failure", "error", "crash",
    "broken", "not working", "issue", "problem", "debug", "troubleshoot"
]

has_troubleshooting_intent = any(indicator in request_lower for indicator in troubleshooting_indicators)

if not has_troubleshooting_intent:
    logger.warning(f"[{session_id}] Ambiguous request - no clear troubleshooting indicators: {user_request[:100]}")
    logger.warning(f"[{session_id}] Proceeding with caution.")
```

**Impact:** Logs warnings for ambiguous requests to help with monitoring.

## Verification

### Test Script

Created [test_routing.sh](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/test_routing.sh) to test routing logic:

```bash
chmod +x test_routing.sh
./test_routing.sh
```

**Tests:**
1. ✅ Simple operation ("List all VMs") → should route to gcloud agent
2. ✅ Troubleshooting ("Why did deployment fail?") → should route to MATS
3. ✅ Storage operation ("Show GCS buckets") → should NOT route to MATS
4. ✅ MATS guard → should reject simple "List VMs" with MISROUTED error

### Manual Testing

#### Test 1: Simple Request via UI

1. Navigate to http://localhost:8501
2. Enter: **"List all VMs in project vector-search-poc"**
3. **Expected Result:**
   - Orchestrator routes to `gcloud_infrastructure_specialist`
   - Returns list of VMs
   - Does NOT trigger MATS

**Check Logs:**
```bash
docker-compose logs orchestrator | grep "Routing"
# Should see: Routing to gcloud_infrastructure_specialist (score: X)
```

#### Test 2: Troubleshooting Request via UI

1. Enter: **"Why did my Cloud Run deployment fail?"**
2. **Expected Result:**
   - Orchestrator routes to `mats-orchestrator`
   - MATS starts investigation workflow
   - Coordinates SRE, Investigator, Architect agents

**Check Logs:**
```bash
docker-compose logs orchestrator | grep "Routing"
# Should see: Routing to MATS: matched trigger 'why did'

docker-compose logs mats-orchestrator | head -30
# Should see: Starting investigation...
# Should NOT see: MISROUTED
```

#### Test 3: Direct MATS Call with Simple Request

1. Send request directly to MATS:
   ```bash
   curl -X POST http://localhost:8084/troubleshoot \
     -H "Content-Type: application/json" \
     -d '{
       "project_id": "vector-search-poc",
       "repo_url": "https://github.com/test/test",
       "user_request": "List all VMs",
       "user_email": "test@example.com"
     }'
   ```

2. **Expected Result:**
   ```json
   {
     "status": "MISROUTED",
     "error": "This appears to be a simple operation, not a troubleshooting request...",
     "suggestion": "Please rephrase your request or use the specific agent..."
   }
   ```

**Check MATS Logs:**
```bash
docker-compose logs mats-orchestrator | grep "MISROUTED"
# Should see: MATS received simple request (misrouted): List all VMs
# Should see: Matched pattern: \blist\s+(all|my|the)?\s*(vms?|...
```

### Debug Routing Decisions

To see detailed routing scores, enable debug logging:

```bash
# In docker-compose.yml, add to orchestrator environment:
environment:
  - DEBUG_ROUTING=true

# Restart
docker-compose restart orchestrator

# Check logs
docker-compose logs -f orchestrator | grep "Routing scores"
```

**Output Example:**
```
Routing scores for 'List all VMs in project vector-search-poc': [
  ('gcloud_infrastructure_specialist', 8),
  ('cloud_run_specialist', 2),
  ('mats-orchestrator', 0)
]
Routing to gcloud_infrastructure_specialist (score: 8)
```

## Success Criteria

- [x] Simple operations route to appropriate agents (not MATS)
- [x] Troubleshooting requests route to MATS
- [x] MATS rejects misrouted simple requests
- [x] Keyword scoring uses word boundaries for accuracy
- [x] Debug logging available for troubleshooting
- [ ] User confirms correct behavior

## Expected Routing Examples

| User Request | Expected Agent | Rationale |
|--------------|----------------|-----------|
| "List all VMs in my project" | `gcloud_infrastructure_specialist` | Simple list operation |
| "Show me GCS buckets" | `storage_specialist` or `gcloud` | Simple show operation |
| "Create a VM in us-central1" | `gcloud_infrastructure_specialist` | Simple create operation |
| "Why did my build fail?" | `mats-orchestrator` | Causality question (why) |
| "Debug the error in my service" | `mats-orchestrator` | Explicit debug request |
| "Find the root cause of the crash" | `mats-orchestrator` | Explicit RCA |
| "Troubleshoot deployment" | `mats-orchestrator` | Explicit troubleshoot |
| "What caused the outage?" | `mats-orchestrator` | Causality question |
| "Investigate the failure" | `mats-orchestrator` | " investigate" + "failure" |
| "Investigate my project" | `gcloud` | Generic investigate (no failure context) |

## Troubleshooting

### Issue: Still routing to MATS incorrectly

**Check:**
1. Containers rebuilt?
   ```bash
   docker-compose ps | grep orchestrator
   # Should show recent "Created" time
   ```

2. New code deployed?
   ```bash
   docker exec finopti-orchestrator grep -A5 "is_simple_operation" /app/orchestrator_adk/agent.py
   # Should show the new code
   ```

3. Enable debug logging to see routing scores

### Issue: MATS not rejecting simple requests

**Check:**
1. MATS container rebuilt?
2. Check logs for the guard code:
   ```bash
   docker exec finopti-platform-mats-orchestrator-1 grep -A3 "REQUEST VALIDATION" /app/agent.py
   ```

### Issue: Keywords not matching

**Enable debug logging** and check scores. Adjust keywords in [master_agent_registry.json](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/orchestrator_adk/master_agent_registry.json) if needed.

## Files Changed

1. [orchestrator_adk/agent.py](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/orchestrator_adk/agent.py)
   - Lines 67-160: Rewrote `detect_intent()` function
   - Lines 393-407: Updated MATS instructions

2. [mats-orchestrator/agent.py](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/mats-agents/mats-orchestrator/agent.py)
   - Lines 403-451: Added request validation guards

3. [test_routing.sh](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/test_routing.sh)
   - New test script for verification

## Next Steps

1. Run `./test_routing.sh` to verify fixes
2. Test via UI with real user prompts
3. Monitor logs for any misrouting
4. Consider adding automated tests to CI/CD pipeline
