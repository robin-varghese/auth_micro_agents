# MATS v2.0 Dry Run Simulation: Cloud Run Failure

**Scenario**: User reports "My Cloud Run service `payment-processor` in project `finopti-prod` is crashing."
**User Context**: Authenticated, `repo_url` known (`github.com/finopti/backend`).

## 1. MATS Orchestrator (The Manager)
**Input**:
- `user_query`: "My Cloud Run service 'payment-processor' in project 'finopti-prod' is crashing."
- `context`: Repo `github.com/finopti/backend`.

**Internal Process (Sequential Thinking)**:
1.  *Thought*: User is reporting a crash. I need to triage.
2.  *Thought*: First, I must confirm the error in logs to get a timestamp and stack trace. (Delegate to SRE).
3.  *Thought*: Then, I need to check the code usage at that stack trace. (Delegate to Investigator).
4.  *Thought*: Finally, I need to create the RCA. (Delegate to Architect).
5.  *Plan Generated*:
    ```json
    [
      {"agent": "mats-sre-agent", "task": "Find error logs for 'payment-processor' in 'finopti-prod' (last 1h)."},
      {"agent": "mats-investigator-agent", "task": "Analyze code based on SRE findings."},
      {"agent": "mats-architect-agent", "task": "Synthesize RCA and publish."}
    ]
    ```

**Action 1**: Call `delegate_to_sre("Find error logs for 'payment-processor'...")`.

---

## 2. MATS SRE Agent (The Triage Lead)
**Input**: "Find error logs for 'payment-processor' in 'finopti-prod' (last 1h)."

**Internal Process**:
1.  *Tool Call*: `read_logs(project_id="finopti-prod", filter="resource.type=cloud_run_revision AND resource.labels.service_name=payment-processor AND severity=ERROR", hours_ago=1)`.
2.  *Tool Output*:
    ```json
    [
      {
        "timestamp": "2026-01-23T14:00:01Z",
        "textPayload": "AttributeError: 'Database' object has no attribute 'connect'",
        "jsonPayload": {"stack_trace": "File 'main.py', line 45, in process_payment"}
      }
    ]
    ```
3.  *Analysis*: Found a critical Python exception in `main.py` related to DB connection.

**Output to Orchestrator**:
> "Confirmed ERROR logs. Found `AttributeError: 'Database' object has no attribute 'connect'` in `main.py` line 45. Timestamp: 14:00:01Z."

---

## 3. MATS Orchestrator (Monitoring Loop)
**Status Update**: "SRE Check Complete. Found code error in `main.py`. Starting Logic Analysis..."

**Action 2**: Call `delegate_to_investigator("Analyze 'main.py' line 45 in repo 'github.com/finopti/backend'. Error: AttributeError 'Database' object has no attribute 'connect'")`.

---

## 4. MATS Investigator Agent (The Detective)
**Input**: "Analyze 'main.py' line 45... Error: AttributeError..."

**Internal Process**:
1.  *Tool Call*: `github_read_file(repo="finopti/backend", path="main.py")`.
2.  *Code Analysis (Line 45)*:
    ```python
    44: db = Database(os.getenv("DB_URL"))
    45: db.connect() 
    ```
3.  *Reasoning*: The error says `Database` object has no `connect` method.
4.  *Tool Call*: `github_read_file(repo="finopti/backend", path="utils/database.py")` (To check the class definition).
5.  *Code Analysis*:
    ```python
    class Database:
        def __init__(self, url):
            self.conn = _internal_connect(url)
        # Missing explicit 'connect' method! It connects in __init__.
    ```
6.  *Conclusion*: The code in `main.py` is calling a deprecated or non-existent method `connect()`. The DB connection happens in `__init__`.

**Output to Orchestrator**:
> "Root Cause identified. Code Defect. `main.py`:45 calls `.connect()`, but `Database` class in `utils/database.py` establishes connection in `__init__` and has no `.connect()` method. This breaks the API contract."

---

## 5. MATS Orchestrator (Monitoring Loop)
**Status Update**: "Investigation Complete. Root Cause: Code Defect (Method signature mismatch). Generating Report..."

**Action 3**: Call `delegate_to_architect(findings=[SRE_Report, Investigator_Report])`.

---

## 6. MATS Architect Agent (The Synthesizer)
**Input**: SRE Logs + Investigator Code Analysis.

**Internal Process**:
1.  *Synthesis*:
    *   **Issue**: CrashLoop in `payment-processor`.
    *   **Cause**: `AttributeError` due to invalid method call.
    *   **Evidence**: Log ID `xyz`, Code Diff `main.py` vs `database.py`.
    *   **Fix Recommendation**: Remove line 45 `db.connect()`.
2.  *Action*: Generate Markdown.
3.  *Tool Call*: `upload_to_GCS(bucket="finopti-reports", filename="rca-payment-20260123.md", content=...)`.
4.  *Output*: URL `https://storage.cloud.google.com/finopti-reports/rca-payment-20260123.md`.

**Output to Orchestrator**:
> "RCA Generated. Access it here: [RCA Document](https://storage.cloud.google.com/finopti-reports/rca-payment-20260123.md)"

---

## 7. MATS Orchestrator (Final Response)
**User Output**:
> "Troubleshooting Complete.
> **Status**: Config/Code Mismatch identified.
> **Summary**: The service crashed because `main.py` calls a non-existent `connect()` method on the Database class.
> **Full Report**: [View RCA](https://storage.cloud.google.com/finopti-reports/rca-payment-20260123.md)"
