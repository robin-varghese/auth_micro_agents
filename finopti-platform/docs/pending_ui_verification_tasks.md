# Implementation Plan - UI Verification Prompts

## Status: ACTIVE
> [!NOTE]
> This plan is now ACTIVE following the successful implementation of all 7 new sub-agents.
> **Brave Search** verification remains DEFERRED (optional) due to missing API key, but **Google Search** takes its place.

## Goal
Update the `finopti-platform/ui` application (`app.py`) to include pre-populated sample prompts that allow the end user to easily verify all newly added capabilities.

## Proposed Changes

### [finopti-platform/ui]
#### [MODIFY] [app.py](file:///Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/ui/app.py)

Add new buttons to the "Sample Prompts" sidebar section for the following agents.
Group them logically (e.g., "New Capabilities").

1.  **Google Search** (Native ADK):
    *   Prompt: `Search google for 'latest Google Cloud Run features'`
2.  **Code Execution** (Native ADK):
    *   Prompt: `Calculate the 100th Fibonacci number using Python`
3.  **Filesystem** (MCP Wrapper):
    *   Prompt: `List files in the current directory`
4.  **Google Analytics** (MCP Wrapper):
    *   Prompt: `Run a report for active users in the last 7 days`
5.  **Puppeteer** (MCP Wrapper):
    *   Prompt: `Take a screenshot of https://www.google.com`
6.  **Sequential Thinking** (ADK Wrapper):
    *   Prompt: `Plan a 3-day itinerary for a trip to Tokyo step-by-step`

### Deferred/Optional Items
-   **Brave Search**: `Search brave for 'privacy focused search engines'`

## Verification Plan

### Manual Verification
1.  **Build**: Run `docker-compose up -d --build` to deploy the updated UI.
2.  **Access**: Open the UI in the browser (localhost:8501).
3.  **Test**: Click each of the new buttons and verify the prompt is populated.
4.  **Execute**: Submit the prompts and verify the agents respond correctly.
