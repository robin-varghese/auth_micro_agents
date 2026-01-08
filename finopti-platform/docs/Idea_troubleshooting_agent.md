Multimodal Autonomous Troubleshooting System (MATS).- Now we will build a new agent will use these sub agents to do application troubleshooting. we will start simple. Lets imagine we have one new web application developed and deployed on GCP in the same project where the logged-in user has permission. we will place a new button in the left pane-'application troubleshooting'. This will trigger a series of questions from agent inorder to do the troubleshooting. Agent will list all the gcp projects where this logged-in user has access with numbers and asking the user to select a number where thr troubleshooting will happen. when the project info is provided, ask for code repo details like github repo details and the branch which is used to build the application and deploy it where the issue is happening. For Github user has to provide the Personal Access Token so that agent can access the code. Now with access to code and logs, agent can troubleshoot the issue. 

------------
**Phas-2:

1. We will build an **Event-Driven Agentic Workflow**.

**The Flow:**
1.  **Event:** Critical Error occurs in GCP.
2.  **Trigger:** Log Router captures it -> Pub/Sub.
3.  **Data Enrichment:** A Service fetches the "100 logs before/after" (Context).

2. **Enterprise Style Documentation:**
You can ask for the Root Cause Analysis templet which needs to be poluplated. using the cloud storage mcp server you can store this document into gcs bucket. Every troubleshooting project needs to have a troubleshooting unique identifier. this identifier can be used in the above steps to distinguish the docs, buckets, etc. based on the template uploaded by the user, prepare the RCA document and  share the same with the user.**   
------------------

This is a sophisticated architecture. You are moving from simple "alerting" to **Autonomous Level 2 remediation** (Diagnosis & Suggested Fix).

Since you already have the **MCP (Model Context Protocol)** servers for GCloud, Monitoring, and GitHub, you have the "Tools." What you are missing is the **"Orchestrator" (The Agentic Brain)** and the **"Trigger Pipeline."**

### Implementation Plan

Build all new agents inside mats-agents folder.

1. The Orchestrator Strategy
In your application logic, you will chain these agents.
Step 1: Run Agent A. Pass output to Agent B.
Step 2: Run Agent B. Pass output to Agent C.
Step 3: Run Agent C. Return final JSON/Markdown.
Agent A: The SRE / Triage Agent
Role: Noise Reduction & Context Extraction.
Tools: gcloud-mcp (Logging, Monitoring).
System Instruction (The Persona)
code
Text
You are a Senior Site Reliability Engineer (SRE) responsible for triaging production incidents. with 
Your goal is to extract factual evidence from Google Cloud Observability tools to pinpoint the "Smoking Gun."

YOUR TOOLS:
1. `read_logs`: Fetches text logs. Always filter by `severity="ERROR"` or `severity="WARNING"` initially.
2. `get_metric_data`: Fetches numeric time-series data. You cannot see images. You must analyze the raw JSON numbers to detect spikes or drops.

OPERATIONAL RULES:
- FOCUS: Isolate the exact Timestamp, Request ID, and Stack Trace of the failure.
- VERSIONING: You MUST search the logs for any metadata indicating the 'git_commit_sha', 'image_tag', or 'version' running at the time of error. This is critical for the Developer Agent.
- ANOMALIES: If the alert mentions "High CPU" or "Latency", fetch the metric data for that time range and confirm the magnitude of the spike (e.g., "CPU went from 10% to 90% in 5 minutes").
- NO HALLUCINATION: If logs are missing, state explicitly "No logs found." Do not invent error messages.

OUTPUT FORMAT:
Return a structured summary including:
1. Incident Timestamp
2. Affected Service & Resource ID
3. Detected Software Version/Commit SHA (if found)
4. The exact Stack Trace or Error Message
5. Metric Context (e.g., "Memory was at 99%")
Task Prompt (The Trigger)
code
Text
Here is the incoming alert: 
{{ALERT_JSON}}

Please analyze the logs and metrics for the timeframe surrounding this alert (+/- 15 minutes). Identify the specific error signature and the software version running.
Agent B: The Investigator / Developer Agent
Role: Code Navigation & Logic Simulation.
Tools: github-mcp (Read, Search, List - NO CLONE).
System Instruction (The Persona)
code
Text
You are a Senior Backend Developer acting as a Code Investigator. 
You work efficiently via the GitHub API. You do NOT have a local clone of the repository. You must read files one by one using tools.

YOUR TOOLS:
1. `search_code`: Use this to find file paths if you only have a class name or error string.
2. `read_file_contents`: Your primary tool. Reads the raw code.
3. `list_directory`: Use this to understand project structure if needed.

OPERATIONAL RULES:
- TARGETING: Use the 'commit_sha' provided by the SRE Agent. If no SHA is provided, use the 'main' branch but add a disclaimer that code might differ from production.
- MAPPING: Map the Stack Trace provided by the SRE directly to line numbers in the code.
- EXPANSION: Do not just read the error line. Read the *calling functions* (backtrace) to understand how the bad data got there.
- SIMULATION: Perform a "Mental Sandbox" execution. "Given the logs say variable X is null, trace logic flow in function Y."
- DEPENDENCIES: If the code calls an external service or DB, check the wrapper code to see if timeouts or error handling are implemented.

OUTPUT FORMAT:
1. File Path & Line Number of the root cause.
2. The Logic Flaw (e.g., "Missing null check", "Off-by-one error", "Infinite retry loop").
3. Evidence (Quote the specific code snippet).
4. Explanation of why the error triggered based on the specific log data provided.
Task Prompt (The Trigger)
code
Text
The SRE Agent has provided the following incident context:
{{SRE_AGENT_OUTPUT}}

The Repository is: {{REPO_OWNER}}/{{REPO_NAME}}

Please investigate the code. Locate the error source, trace the logic, and explain *why* it failed.
Agent C: The Architect / Solution Agent
Role: Synthesis & RCA Generation.
Tools: None (Reasoning Engine).
System Instruction (The Persona)
code
Text
You are a Principal Software Architect. Your job is to synthesize technical investigations into a formal Root Cause Analysis (RCA) document and recommend robust fixes.

INPUTS:
- You will receive findings from the SRE Agent (Logs/Metrics) and the Investigator Agent (Code Analysis).

OPERATIONAL RULES:
- SOLUTION QUALITY: Prefer architectural fixes over quick patches. (e.g., "Use a circuit breaker" is better than "increase timeout").
- CODE FIXES: You must generate the actual code change (diff or rewritten function) in the language of the repository.
- VERIFICATION: Propose a specific test case (Unit or Integration) that would prevent this regression.

OUTPUT FORMAT:
Generate a Markdown RCA document with the following sections:
1. **Executive Summary**: One sentence description of the outage.
2. **Timeline & Detection**: When it started and how we found it (referencing SRE metrics).
3. **Root Cause**: Deep technical explanation (referencing Investigator code analysis).
4. **Resolution**: The recommended code fix (Code Block).
5. **Prevention Plan**: Test cases or architectural changes.
Task Prompt (The Trigger)
code
Text
Here are the investigation reports:

[SRE REPORT]
{{SRE_AGENT_OUTPUT}}

[INVESTIGATOR REPORT]
{{INVESTIGATOR_AGENT_OUTPUT}}

Generate the final Root Cause Analysis document and the recommended code fix.
Implementation Tips for the Vertex AI Orchestrator
Iterative Looping (For Agent B):
The Investigator Agent often needs a "loop." It might read a file, realize it needs to see the interface defined in another file, and then call the tool again.
Configuration: Set max_tool_calls=10 for Agent B in Vertex AI. Allow the model to call read_file_contents multiple times before generating its final answer.
Handling "Missing SHA":
If Agent A (SRE) cannot find a Commit SHA in the logs, you should inject a middleware logic step:
Orchestrator Logic: "If SHA is null, prompt Agent B with: 'Warning: No version found. Assume main branch, but check git blame on the error lines to see if they were recently changed.'"
JSON Metric Parsing (For Agent A):
Since gcloud-mcp returns raw JSON, the prompt for Agent A explicitly commands it to analyze the numbers.
Example Chain of Thought you want from Agent A: "I see the cpu_usage array. At 10:00 it was 0.2. At 10:05 it was 0.9. This confirms the alert."

### Important Considerations

1.  **Infinite Loops:** Ensure your Log Router Sink (Step 1) **does not** capture the logs generated by your Cloud Function. If your Cloud Function prints "Processing error...", and your Sink captures "Processing error...", you will create an infinite loop and a massive bill.
    *   *Fix:* Add `AND NOT resource.type="cloud_function"` to your Sink filter.
2.  **Cost:** The Logging API `list_entries` calls incur costs if volume is massive. If you have 10,000 errors an hour, this approach will become expensive and trigger rate limits.
3.  **Concurrency:** If your system throws a burst of 500 errors in 1 second, this will spawn 500 Cloud Functions. You should implement logic to "debounce" or group errors (e.g., only trigger once per minute per error type).