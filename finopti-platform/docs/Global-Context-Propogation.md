This implementation plan is designed for the Google Antigravity/ADK framework and Gemini 2.0/3.0 Pro. It outlines how to build a unified observability fabric across your 40+ agents and 12 MCP servers using Arize Phoenix and OpenInference.
Technical Implementation Plan: Unified Agentic Observability & Context Propagation
1. Objective
Establish a single "Trace Thread" that links multi-agent reasoning, MCP tool calls, and microservice hops into a single visual waterfall in Arize Phoenix, capturing both "what" happened and "why" (RCA logic).
2. Core Architecture Components
Observability Backend: Arize Phoenix (Self-hosted via Docker).
Instrumentation Standard: OpenInference (OTLP).
Trace Initiator: UI Agent (Gateway).
Context Carrier: W3C TraceContext (traceparent) + OTel Baggage.
State Store: Redis (for ADK Session persistence across containers).
3. Step-by-Step Execution Instructions
Phase A: The Infrastructure Foundation
Directive for Gemini: “Configure the Docker swarm environment to support a centralized OTel Collector and an Arize Phoenix instance.”
Deploy OTel Collector: Create a central container that receives OTLP traces from all 40 agents and 12 MCP servers.
Phoenix Setup: Initialize Arize Phoenix with an OTLP endpoint enabled.
ADK Custom Session: Implement a RedisSessionService in ADK to replace InMemorySessionService, ensuring that when Agent 15 picks up a task, it can access the same session state as Agent 1.
Phase B: Global Context Propagation (The "Single Thread")
Directive for Gemini: “Implement a context propagation layer that ensures the trace_id generated at the UI is passed through all downstream microservices.”
UI Root Span: At the start of an RCA workflow, the UI Agent must generate the Root Span.
Propagation Middleware:
Every Agent-to-Agent call must include the traceparent header.
In ADK, use the on_dispatch hook to inject current trace context into the payload of the next agent call.
The "New Workflow" Trigger:
Expose a /start-rca endpoint.
If no traceparent is provided, generate a new one.
If a traceparent is provided (e.g., from a 'Resume' button), extract it to continue the thread.
Phase C: ADK & OpenInference Instrumentation
Directive for Gemini: “Instrument the 40 ADK agents using openinference-instrumentation-google-adk to capture reasoning and metadata.”
Capture Reasoning: Map the agent.thought or reasoning_path to the openinference.span.kind = "CHAIN" attribute.
Metadata Injection: For every span, automatically attach:
incident.id: Link to the cloud incident.
service.target: The service being investigated.
session.id: The ADK session GUID.
RCA Document Finalization: When the final .md or .pdf is generated, create a "Final Span" that includes the document summary as a span attribute for quick preview in Phoenix.
Phase D: MCP Server Bridge
Directive for Gemini: “Bridge the gap between ADK Agents and the 12 MCP Servers to ensure tool calls are nested correctly.”
MCP Client Instrumentation: Use the MCPToolset wrapper to extract the current OTel trace_id and inject it into the _meta field of the MCP JSON-RPC call.
MCP Server Extraction: Ensure the 12 MCP servers are configured to look for traceparent in the incoming metadata.
Tool I/O Logging: Capture the raw JSON input/output of every MCP tool call to debug data-source failures in the RCA process.
4. Implementation Snippets for Gemini 3.0 Pro
Context-Aware Agent Wrapper (Python/ADK)
code
Python
from opentelemetry import trace, propagate
from openinference.instrumentation.google_adk import AdkInstrumentor

# 1. Initialize Instrumentation
AdkInstrumentor().instrument()

def execute_agent_workflow(request):
    # 2. Extract context from UI or Previous Agent
    context = propagate.extract(request.headers)
    
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("Agent_Reasoning_Step", context=context):
        # 3. Use current span as parent for ADK session
        current_span = trace.get_current_span()
        trace_id = current_span.get_span_context().trace_id
        
        # 4. Attach RCA Metadata
        current_span.set_attribute("incident.id", request.json.get("incident_id"))
        
        # 5. Call ADK Agent
        agent_response = adk_agent.run(input=request.json['prompt'], session_id=str(trace_id))
        return agent_response
MCP Metadata Injection
code
Python
# Logic to be implemented in the Tool calling mechanism
def call_mcp_tool(tool_name, args):
    headers = {}
    propagate.inject(headers) # Injects 'traceparent'
    
    mcp_payload = {
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": args,
            "_meta": {
                "traceparent": headers.get("traceparent")
            }
        }
    }
    # Send to MCP Server container...
5. Success Metrics for the Agent
Trace Continuity: A single Trace ID is visible in Arize Phoenix for an entire RCA journey involving multiple agents.
Reasoning Transparency: The "Thoughts" of the agents appear as spans in the Phoenix UI.
Zero Loss: Every one of the 12 MCP servers reports its internal execution as a child span of the calling agent.
RCA Linkage: Searching for an incident_id in Phoenix returns exactly one complete trace of the multi-agent swarm.