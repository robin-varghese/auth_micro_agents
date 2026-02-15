# Orchestrator ADK — Code Refactoring Guideline

**Scope:** [agent.py](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/orchestrator_adk/agent.py) (810 lines → target ~250 lines)  
**Aligned with:** [AI_AGENT_DEVELOPMENT_GUIDE.md](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/AI_AGENT_DEVELOPMENT_GUIDE.md) v5.0

---

## 1. Current Structure & Problems

`agent.py` currently holds **7 distinct responsibilities** in a single file:

| Lines | Responsibility | Size | Problem |
|-------|---------------|------|---------|
| 1–57 | Imports, Observability | ~60 | Mixes config, logging, and side-effects |
| 58–87 | ContextVars + Progress | ~30 | Duplicated across platform |
| 88–113 | Registry Management | ~25 | Global state `_AGENT_REGISTRY` |
| 116–219 | Intent Detection | ~100 | Huge regex logic, hard to test in isolation |
| 221–254 | Authorization (OPA) | ~35 | External service call mixed with agent logic |
| 256–461 | Routing & Execution | ~205 | Complex retry logic, APISIX mapping, MATS handling |
| 463–605 | App Factory & Prompts | ~140 | Massive prompt string hides the factory logic |
| 608–756 | Request Processing | ~150 | Core entry point (Keep this) |

---

## 2. Module Decomposition Map

Extract to these new/existing files. Each module is independently testable.

```
orchestrator_adk/
├── agent.py              # CORE: App factory, process_request_async, entrypoint
├── main.py               # Entrypoint (unchanged)
│
├── observability.py      # [NEW] Phoenix setup, tracer (consistent with MATS)
├── context.py            # [NEW] ContextVars, _report_progress helper (consistent with MATS)
├── registry.py           # [NEW] load_registry(), get_agent_by_id()
├── intent.py             # [NEW] detect_intent() regex logic
├── auth.py               # [NEW] check_opa_authorization()
├── routing.py            # [NEW] route_to_agent() with retry & APISIX logic
├── instructions.py       # [NEW] Agent System Prompt & Description
```

---

## 3. Extraction Rules

### Rule A: `agent.py` Retains Only Core Capabilities

After refactoring, `agent.py` should contain **only**:

1. **Imports** from new modules
2. **`create_app()`** — Agent definition + App factory
3. **`process_request_async()`** — High-level workflow orchestration
4. **`process_request()`** — Sync wrapper

Everything else is imported.

### Rule B: No Business Logic in Module-Level Code

Module-level code (runs at import time) should be limited to:
- `import` statements
- Logger initialization
- **One** call to `setup_observability()` (from `observability.py`)

---

## 4. Detailed Extraction Specs

### 4.1 `observability.py`
**Extract from:** Lines 46–57  
**Exports:** `setup_observability()`, `tracer`

```python
# Encapsulate Phoenix registration to avoid side-effects on import
def setup_observability():
    ...
```

### 4.2 `context.py`
**Extract from:** Lines 58–87  
**Exports:** `_session_id_ctx`, `_user_email_ctx`, `_redis_publisher_ctx`, `_report_progress()`

Standard component shared with MATS Orchestrator.

### 4.3 `registry.py`
**Extract from:** Lines 88–113  
**Exports:** `load_registry()`, `get_agent_by_id()`

Remove the `global _AGENT_REGISTRY` if possible, or keep it scoped within the module.

### 4.4 `intent.py`
**Extract from:** Lines 116–219  
**Exports:** `detect_intent(prompt)`

Pure logic function. Easy to unit test.

### 4.5 `auth.py`
**Extract from:** Lines 221–254  
**Exports:** `check_opa_authorization(user_email, target_agent)`

Encapsulate the HTTP call to OPA.

### 4.6 `routing.py`
**Extract from:** Lines 256–461  
**Exports:** `route_to_agent(...)`

This is the heaviest extraction. It contains `requests` logic, retry loops, and screenshot chaining.
Ensure all imports (`requests`, `json`, `time`) follow it.

### 4.7 `instructions.py`
**Extract from:** Lines 478–577 (The huge string)  
**Exports:** `ORCHESTRATOR_INSTRUCTIONS`, `ORCHESTRATOR_DESCRIPTION`

Keep `agent.py` clean by moving the prompt text here.

---

## 5. Target `agent.py` Structure

```python
"""
Orchestrator ADK Agent - Central Hub
"""
import sys
# ... imports ...
from observability import setup_observability
from context import _session_id_ctx, _report_progress
from registry import load_registry
from intent import detect_intent
from auth import check_opa_authorization
from routing import route_to_agent
from instructions import ORCHESTRATOR_INSTRUCTIONS, ORCHESTRATOR_DESCRIPTION

setup_observability()

def create_app():
    # ... uses ORCHESTRATOR_INSTRUCTIONS ...
    
async def process_request_async(...):
    # ... uses detect_intent, check_opa, route_to_agent ...
```

---

## 6. Execution Order

Refactor in this order to minimize risk:

| Step | Module | Risk | Lines Removed |
|------|--------|------|---------------|
| 1 | `registry.py` & `intent.py` | Low | ~130 |
| 2 | `auth.py` & `routing.py` | Medium | ~240 |
| 3 | `context.py` & `observability.py` | Low | ~40 |
| 4 | `instructions.py` | Low | ~100 |
| **Total** | | | **~510 lines** |

---

## 7. Verification Checklist

- [ ] `python -c "from agent import create_app"` succeeds
- [ ] OPA checks still work
- [ ] Routing to `gcloud` works
- [ ] Routing to `mats-orchestrator` works
- [ ] Observability traces appear in Phoenix
