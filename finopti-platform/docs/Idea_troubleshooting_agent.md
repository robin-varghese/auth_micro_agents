Now we will build a new agent will use these sub agents to do application troubleshooting. we will start simple. Lets imagine we have one new web application developed and deployed on GCP in the same project where the logged-in user has permission. we will place a new button in the left pane-'application troubleshooting'. This will trigger a series of questions from agent inorder to do the troubleshooting. Agent will list all the gcp projects where this logged-in user has access with numbers and asking the user to select a number where thr troubleshooting will happen. when the project info is provided, ask for code repo details like github repo details and the branch which is used to build the application and deploy it where the issue is happening. For Github user has to provide the Personal Access Token so that agent can access the code. Now with access to code and logs, agent can troubleshoot the issue. You can ask for the Root Cause Analysis templet which needs to be poluplated. using the cloud storage mcp server you can store this document into gcs bucket. Every troubleshooting project needs to have a troubleshooting unique identifier. this identifier can be used in the above steps to distinguish the docs, buckets, etc. based on the template uploaded by the user, prepare the RCA document and  share the same with the user.   

This is a sophisticated architecture. You are moving from simple "alerting" to **Autonomous Level 2 remediation** (Diagnosis & Suggested Fix).

Since you already have the **MCP (Model Context Protocol)** servers for GCloud, Monitoring, and GitHub, you have the "Tools." What you are missing is the **"Orchestrator" (The Agentic Brain)** and the **"Trigger Pipeline."**


---

### The Architecture: "The Autonomic SRE Platform"

We will build an **Event-Driven Agentic Workflow**.

**The Flow:**
1.  **Event:** Critical Error occurs in GCP.
2.  **Trigger:** Log Router captures it -> Pub/Sub.
3.  **Data Enrichment:** A Service fetches the "100 logs before/after" (Context).
4.  **The Agent Swarm (MCP Host):**
    *   **Agent A (SRE):** Analyzes the logs via Monitoring MCP.
    *   **Agent B (Dev):** Locates the code via GitHub MCP.
    *   **Agent C (Architect):** Synthesizes the fix and writes the RCA.
5.  **Output:** A Pull Request or a PDF Report sent to Slack/Jira.

---

### Implementation Plan

#### Phase 1: Infrastructure & Automation (The Trigger)
*Goal: Catch the error and package the raw data.*

You need a lightweight "Pre-processor" before waking up the AI Agents to save cost and latency.

1.  **Log Sink:** Configure Cloud Logging to send `severity="ERROR"` to a Pub/Sub topic named `sre-investigation-trigger`.
2.  **Context Fetcher (Cloud Function):**
    *   Deploy the Python script I shared in the previous answer as a Cloud Function.
    *   **Modification:** Instead of just printing the logs, this function should payload the **Error Log + 100 Before + 100 After** into a JSON object.
    *   **Action:** It sends this JSON payload to your **MCP Orchestrator** (hosted on Cloud Run).

#### Phase 2: The MCP Orchestrator (The Brain)
*Goal: A "Headless" MCP Host that connects your existing MCP Servers to Gemini.*

Since MCP is usually client-server (like Claude Desktop connecting to a server), you need a **Custom MCP Host** application running on Cloud Run. This app receives the webhook from Phase 1 and instantiates the Agents.

**Technology:** Python (LangGraph or PydanticAI) + Vertex AI SDK (Gemini 3.0 Pro).

**The Workflow Code Logic:**

1.  **Receive Context:** The Host receives the 201 logs (1 error + 100 before/after).
2.  **Initialize Gemini 3.0 Pro:** You need the 1M+ token window to dump all 200 logs and potential code files into the context.

#### Phase 3: Agentic Capabilities & Prompt Engineering
*Goal: Define the specific jobs for the AI.*

You will chain three logical steps (or Agents) using your existing MCP tools.

**Step 1: The Log Analyst (Uses Google Monitoring MCP)**
*   **Input:** The 201 log entries.
*   **Task:** "Analyze the stack trace. Identify the exact error message. Identify the file path and line number causing the crash. Identify if this is an Infrastructure issue (OOM, Quota) or Code issue (NullPointer, Syntax)."
*   **Tool Usage:** If the logs aren't enough, use the *Monitoring MCP* to check CPU/RAM metrics at that specific timestamp.

**Step 2: The Code Investigator (Uses GitHub MCP)**
*   **Input:** File path and Line number from Step 1.
*   **Task:** "Fetch the file content from the repository. Also, fetch any imported files that are referenced on the error line."
*   **Tool Usage:** Calls `github_mcp.read_file`, `github_mcp.search_code`.

**Step 3: The Root Cause Architect (Uses Vertex AI Reasoning)**
*   **Input:** The Logs + The Source Code.
*   **Task:** "Correlate the log timestamps with the code logic. Why did the code fail given the inputs seen in the logs? Write a fix."

#### Phase 4: Output Generation
*Goal: The Comprehensive Document.*

The final Agent is tasked with generating the Markdown/PDF. Here is the structure you should program the System Prompt to produce:

1.  **Executive Summary:** 1-sentence description of the failure.
2.  **Root Cause Analysis:**
    *   **Trigger:** (e.g., "User uploaded a CSV with a missing header.")
    *   **Code Trace:** (e.g., "Line 45 in `data_parser.py` attempts to access index 0 of an empty array.")
3.  **Evidence:**
    *   *Extract of Log:* (Show the specific exception).
    *   *Extract of Code:* (Show the buggy function).
4.  **Remediation:**
    *   **The Fix:** (e.g., "Add a check for empty array before accessing index.")
    *   **Sample Code:** (Provide the actual Python/Node/Go code block).
5.  **Impact:** (e.g., "This affected the Import Service for 15 minutes.")

---

### Integration of Google Technologies

To answer your specific question on integration:

1.  **Google Vertex AI (Gemini 1.5 Pro):**
    *   **Status:** **Crucial.**
    *   **Why:** You are passing huge amounts of text (logs + code). GPT-4 or smaller models might truncate context. Gemini 1.5 Pro has a 2-million token window. You can literally feed it the *entire* related source code folder and the *entire* log stream without summarization.
    *   **Integration:** Use `vertexai.generative_models.GenerativeModel("gemini-1.5-pro")` in your Python Orchestrator.

2.  **Google Monitoring MCP:**
    *   **Status:** **Crucial.**
    *   **Integration:** Your Orchestrator calls this to fetch extra metric data (e.g., "Was CPU spiking when the log error happened?").

3.  **Gemini CLI:**
    *   **Status:** **Not needed.**
    *   **Why:** CLI is for interactive shell use. You are building an API-driven automation platform. Use the SDKs.

### Summary of Deployment

1.  **GCP Project:**
    *   **Pub/Sub Topic:** `error-events`
    *   **Cloud Function:** `log-aggregator` (fetches the 100 logs -> pushes to Orchestrator).
    *   **Cloud Run:** `agent-orchestrator` (The Python app running LangGraph + Vertex AI SDK + MCP Clients).
2.  **MCP Configuration:**
    *   Ensure your Cloud Run service has IAM permissions to invoke the Monitoring and GCloud APIs.
    *   Ensure your Cloud Run service has the GitHub Private Key/Token mounted as a secret to invoke the GitHub MCP.

This architecture creates a fully automated "Level 2 Support Engineer" that wakes up on error, reads the logs, reads the code, and hands you a fix on a silver platter.


Robin: In Google cloud, when any error/exception is reported, is there any trigger reported or can it be captured. If any trigger can be set, Can I request to get 100 log entries before and after the error?

Yes, you can achieve this in Google Cloud, but it is **not a built-in "checkbox" feature**. There is no single setting that says "Send me an email with the error and 100 surrounding logs."

Instead, you must build an **Event-Driven Architecture** to orchestrate this.

Here is the step-by-step solution to set up a trigger and capture the 100 logs before and after an event.

### The Architecture

1.  **Log Router (The Trigger):** Filters for the specific error/exception.
2.  **Pub/Sub (The Transport):** Passes the error log data to a processor.
3.  **Cloud Functions (The Processor):** Receives the error, extracts the timestamp, and queries the Logging API for the surrounding entries.

---

### Step 1: Create the Trigger (Log Router Sink)

You need to tell Google Cloud to react when a specific error occurs.

1.  Go to **Cloud Logging** -> **Log Router**.
2.  Click **Create Sink**.
3.  **Sink Name:** `error-context-capture`.
4.  **Destination:** Select **Cloud Pub/Sub topic** (Create a new topic, e.g., `error-trigger-topic`).
5.  **Inclusion Filter:** Define exactly what triggers this.
    *   Example: `severity="ERROR" AND resource.type="k8s_container"`
6.  Create the Sink.

### Step 2: Create the Processor (Cloud Function)

You need a script to perform the logic of fetching the "before" and "after" logs.

1.  Go to **Cloud Functions**.
2.  Create a new function (2nd Gen is recommended).
3.  **Trigger:** Cloud Pub/Sub (select the `error-trigger-topic` you created in Step 1).
4.  **Runtime:** Python (e.g., Python 3.10+).

### Step 3: The Logic (Fetching 100 Logs Before/After)

This is the critical part. Inside the Cloud Function, you will use the **Cloud Logging Client Library**.

When the error happens at timestamp $T$:
*   **To get 100 logs *Before*:** Query logs where `timestamp < T`, sort `DESC`, limit 100.
*   **To get 100 logs *After*:** Query logs where `timestamp > T`, sort `ASC`, limit 100.

**Important Note on "After" Logs:** If the error *just* happened, the logs for the next few seconds might not be ingested yet. Your function might need to wait (sleep) for 10-20 seconds before querying for the "After" logs, or the result might be empty.

#### Python Code Example for the Cloud Function

Add `google-cloud-logging` to your `requirements.txt`.

```python
import base64
import json
import time
from google.cloud import logging_v2
from google.cloud.logging_v2 import ASCENDING, DESCENDING

def capture_log_context(event, context):
    """Triggered from a message on a Cloud Pub/Sub topic."""
    
    # 1. Parse the incoming Pub/Sub message to get the Error Log details
    pubsub_message = base64.b64decode(event['data']).decode('utf-8')
    error_log_entry = json.loads(pubsub_message)
    
    # Extract details
    error_timestamp = error_log_entry.get('timestamp')
    insert_id = error_log_entry.get('insertId')
    resource = error_log_entry.get('resource')
    
    print(f"Processing error: {insert_id} at {error_timestamp}")

    # Initialize Client
    client = logging_v2.Client()
    
    # Define the filter scope (e.g., limit to the same specific resource/container)
    # This ensures we get context for THIS app, not global project logs
    resource_filter = f'resource.type="{resource.get("type")}"'
    if 'labels' in resource:
        for key, val in resource['labels'].items():
            resource_filter += f' AND resource.labels.{key}="{val}"'

    # ---------------------------------------------------------
    # 2. Fetch 100 Logs BEFORE the error
    # ---------------------------------------------------------
    filter_before = f'{resource_filter} AND timestamp < "{error_timestamp}"'
    
    logs_before = list(client.list_entries(
        filter_=filter_before,
        order_by=DESCENDING, # Get the closest ones first
        page_size=100
    ))
    
    # Reverse to put them in chronological order
    logs_before.reverse() 

    # ---------------------------------------------------------
    # 3. Fetch 100 Logs AFTER the error
    # ---------------------------------------------------------
    # Wait briefly to ensure subsequent logs are ingested (optional but recommended)
    time.sleep(15) 
    
    filter_after = f'{resource_filter} AND timestamp > "{error_timestamp}"'
    
    logs_after = list(client.list_entries(
        filter_=filter_after,
        order_by=ASCENDING,
        page_size=100
    ))

    # ---------------------------------------------------------
    # 4. Output or Save the Data
    # ---------------------------------------------------------
    full_context = logs_before + [error_log_entry] + logs_after
    
    # Example: Write to a storage bucket, send to Slack, or print to stdout
    print(f"Captured {len(full_context)} log entries surrounding the error.")
    
    # Logic to export the 'full_context' list goes here
```

### Important Considerations

1.  **Infinite Loops:** Ensure your Log Router Sink (Step 1) **does not** capture the logs generated by your Cloud Function. If your Cloud Function prints "Processing error...", and your Sink captures "Processing error...", you will create an infinite loop and a massive bill.
    *   *Fix:* Add `AND NOT resource.type="cloud_function"` to your Sink filter.
2.  **Cost:** The Logging API `list_entries` calls incur costs if volume is massive. If you have 10,000 errors an hour, this approach will become expensive and trigger rate limits.
3.  **Concurrency:** If your system throws a burst of 500 errors in 1 second, this will spawn 500 Cloud Functions. You should implement logic to "debounce" or group errors (e.g., only trigger once per minute per error type).