# FinOpti Platform Roadmap

This document outlines the planned tasks for the FinOpti platform, prioritized to deliver immediate value while building towards an autonomous enterprise-grade SRE system.

## Phase 1: Foundations & Cleanup (Immediate Priority)
*Focus: Stabilization, Security, and Session Context.*

1.  **Always-Ready Demo & Collaboration Strategy**: Establish branch protection and CI/CD basics to ensure the platform is always in a "demoable" state.
2.  **Session Persistence**: Store core incident metadata (Project ID, Incident ID) in the Redis session layer.
3.  **Context-Aware MATS**: Update the MATS orchestrator to leverage session metadata for smarter tool selection.
4.  **Session & Channel Cleanup**: Implement automated resource cleanup and channel clearance post-session.
5.  **Agent-Native Operations**: Remove hard-coded GCP CLI calls; transition all operations to built-in agents and MCP tools.
6.  **Safety Guardrails**: Implement policy enforcement to prevent agents from executing destructive system or cloud commands.

## Phase 2: Core Capability Enhancement
*Focus: UX, Standardized Remediation, and Depth of Analysis.*

7.  **Interactive Triage**: Enhance the orchestrator to interactively prompt users for repo details, branches, and incident context.
8.  **Standardized Remediation (JSON)**: Move to a structured JSON format for remediation steps to enable automated validation.
9.  **CoT Remediation**: Add "Chain of Thought" (Thinking) capabilities to the remediation agent for complex troubleshooting logic.
10. **Code Analysis & Fix Specialists**: Integrate specialist agents for deep code inspection and automated bug fixing.
11. **GCP Service Catalog**: Implement a discovery tool to list active GCP services, narrowing the triage scope.

## Phase 3: Presentation & Integration
*Focus: Aesthetics and Professional Workflows.*

12. **Aesthetic Document Agent**: A dedicated agent for generating high-fidelity, visually impressive RCA and Remediation documents (PDF/HTML).
13. **V2 Agent Guide**: Update developer documentation to standardise ADK V2 patterns and OTel instrumentation.
14. **GKE Specialist**: Integrate a Kubernetes-specific MCP server for deep GKE observability.
16. **Mantis Integration**: Build a dedicated MCP server for Mantis bug tracker integration.
17. **Grafana Observability Portal**: Build an MCP server for native Grafana integration and an agentic chat interface to simplify system observability.
18. **Bug-to-Troubleshoot Workflow**: Enable triggering the troubleshooting flow directly from Mantis tickets.
19. **Closed-Loop Remediation**: Automate the updates and closing of Mantis tickets upon incident resolution.

## Phase 4: Intelligence & Scale
*Focus: Autonomy, Predictive Analytics, and Enterprise Resilience.*

18. **Vector Knowledge Base**: Implement MongoDB + Vector search to store and retrieve historical RCA data for reuse.
19. **Modern Observability Backend**: Transition from BigQuery to MongoDB for faster, real-time analytics during RCA generation.
20. **Cloud-Native Triggers (PubSub)**: Enable autonomous troubleshooting by subscribing to GCP Log Router exports.
21. **Predictive Analytics Agent**: Leverage historical data in MongoDB to identify outage patterns and suggest preemptive fixes.
22. **Enterprise Surge Protection**: Implement throttling and deduplication for high-volume outage triggers.
23. **100+ Chaos Use-Cases**: Expand Chaos Monkey to cover complex failure modes (Latency, IAM, Pod Evictions).
24. **Executive Insights Agent**: Generate automated high-level reporting and dashboards for leadership teams.
