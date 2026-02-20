# Session State & Context Management

The FinOptiAgents Platform uses a dual-layer state management system to ensure that troubleshooting metadata is conserved across different agents while maintaining high-performance, fine-grained investigation state for the troubleshooting engine.

## 1. Architecture Overview

Session state is split across two primary Redis key namespaces, managed by different components:

| Feature | `context:session:[ID]` | `session:[ID]` |
| :--- | :--- | :--- |
| **Common Name** | Global Context | Investigation State |
| **Owner** | **Redis Gateway** | **MATS Orchestrator** |
| **Purpose** | High-level application metadata | Deep investigation lifecycle |
| **Persistence** | 24 Hours (TTL) | Persistent (until manual reset) |

---

## 2. Global context (`context:session:*`)

Stored in Redis and accessible via the **Redis Gateway API**. This layer acts as the "source of truth" for the application being investigated.

### **Data Structure**
```json
{
  "environment": "dev",
  "project_id": "vector-search-poc",
  "application_name": "calculator-app",
  "repo_url": "https://github.com/robin-varghese/calculator-app.git",
  "repo_branch": "main",
  "github_pat": "ghp_***",
  "iam_status": "VERIFIED",
  "last_updated": "2026-02-18T21:18:15Z"
}
```

### **Usage by Agents**
- **Routing Orchestrator**: Reads this context before delegating a request to a sub-agent. If the user refers to "the application," the orchestrator looks up these details to fill in the sub-agent's parameters.
- **IAM Agent**: Uses the `project_id` and `user_email` from this context to verify permissions.
- **SRE/Investigator Agents**: Receive these fields from the Orchestrator so they know which repo to clone and which project to query logs from.

---

## 3. Investigation State (`session:*`)

Stored directly in Redis by the **MATS Orchestrator** (the brain behind the MATS agents). This layer tracks the logic, findings, and progress of the specific troubleshooting journey.

### **Data Structure**
```json
{
  "session_id": "827...",
  "workflow": {
    "current_phase": "triage",
    "phase_transitions": [...]
  },
  "sre_findings": {
    "error_logs": "...",
    "metrics": "..."
  },
  "investigator_findings": {
    "code_snippet": "...",
    "fix_suggestion": "..."
  },
  "confidence_scores": {
    "sre": 0.9,
    "investigator": 0.85
  },
  "status": "IN_PROGRESS"
}
```

### **Usage by Agents**
- **MATS Orchestrator**: Uses this to manage the multi-agent chain (SRE -> Investigator -> Architect). It ensures that Agent B (Investigator) has access to the logs found by Agent A (SRE).
- **Architect Agent**: Reads the accumulated findings from this object to generate the final Root Cause Analysis (RCA) document.

---

## 4. Interaction Flow

1.  **Initialization**: The UI initializes the **Global Context** (`context:session:*`) via the Redis Gateway when the user provides application details.
2.  **Routing**: The **Routing Orchestrator** receives a user prompt. It fetches the Global Context to understand the target project/application.
3.  **Troubleshooting**: If it routes to MATS, the **MATS Orchestrator** either creates or loads the **Investigation State** (`session:*`).
4.  **Propagation**: During the investigation, MATS sub-agents (SRE, Investigator) are called. They receive metadata from the Global Context (like GitHub PAT) but save their specific findings into the Investigation State.
5.  **Completion**: The Architect Agent uses the Investigation State to finalize the RCA, and the overall status is updated in both layers.

This separation ensures that the Routing Orchestrator remains a lightweight "router," while the MATS engine can handle complex, stateful investigation logic independently.
