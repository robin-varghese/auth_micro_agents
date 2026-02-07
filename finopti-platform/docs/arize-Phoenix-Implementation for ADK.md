Implementing Arize Phoenix (and the OpenInference standard) into a microservices-based, multi-agent platform requires a specialized set of data points. Because your system's final output is an RCA (Root Cause Analysis) document, your observability must not only track what happened but why a specific reasoning path was chosen.
To get the best observability for 40+ agents and 12 MCP servers, you should capture data across these four layers:
1. The Reasoning & Flow Layer (Agent Context)
Since you have 40 agents, the most critical data point is identifying "who is doing what" in the swarm.
agent.name / agent.role: Essential for the "Agent Graph" in Phoenix to visualize handoffs.
session_id: Map this to your ADK session. This allows you to group all 40 agents' work under one user request.
workflow.name: Differentiate between different RCA logic paths (e.g., "Network Troubleshooting" vs "Database Latency").
reasoning.content: If your agents use Chain-of-Thought (CoT), capture the raw "thoughts" as a span attribute. This is vital for debugging why an agent hallucinated a root cause.[1]
2. The Interaction Layer (MCP & Tool Calls)
Your 12 MCP servers are currently "black boxes." You need to capture the inputs and outputs of these tool calls to see if an agent failed because the MCP server provided bad data.
tool.name & tool.description: The name of the MCP tool called.
tool.parameters / tool.input: The JSON arguments passed to the MCP server.
tool.output: The raw response from the MCP server.
mcp.server_id: Since you have 12 servers, track which container handled the request for load balancing and reliability analysis.
Propagation Headers: Use openinference-instrumentation-mcp to ensure the traceparent is passed from the Agent container to the MCP container. This unifies the trace.[2][3][4]
3. The Performance Layer (LLM & Infrastructure)
These are standard but critical for cost and latency optimization.
llm.model_name: Track if GPT-4o is doing the heavy lifting vs. a cheaper model for sub-tasks.
llm.token_count.prompt / completion: Calculate the cost of generating a single RCA document.
llm.latency: Identify which of the 40 agents is the bottleneck.
llm.invocation_parameters: Capture temperature, top_p, etc., to see if high "creativity" settings are causing inconsistent RCA outputs.
4. The RCA Metadata Layer (Business Context)
To make your observability actionable for your specific platform, attach your domain-specific metadata.
incident.id: Link the trace directly to the cloud incident being investigated.
target.service_id: The service the agent is troubleshooting.
rca.status: (Success/Failure/Partial) Use this to filter traces in Phoenix to find only "failed" RCA attempts for manual review.
evaluation.score: If you have an automated "grader" agent that checks the RCA document's quality, log that score as an attribute on the root span.
Implementation Strategy for ADK
Since you are using Google ADK, you can leverage its lifecycle hooks to inject these data points without refactoring your agent logic:
Use before_tool hook: To capture the exact arguments sent to your MCP servers.
Use on_model_error hook: To log rate-limiting or hallucination errors directly into Phoenix.
OTel Collector: Deploy a single otel-collector container in your Docker swarm. Configure all 40 agents and 12 MCP servers to send traces to this collector, which then exports them to your Arize Phoenix instance.
Why this works for your RCA platform:
When an agent generates a "wrong" RCA document, you can go into Phoenix, search by the incident.id, and see a high-level graph. You will see exactly which of the 40 agents veered off-track or which of the 12 MCP servers returned a null value that broke the reasoning chain.