import re

FILES_AGENT = [
    "analytics_agent_adk/agent.py",
    "puppeteer_agent_adk/agent.py",
    "sequential_thinking_agent_adk/agent.py",
    "googlesearch_agent_adk/agent.py",
    "filesystem_agent_adk/agent.py",
    "brave_search_agent_adk/agent.py"
]

FILES_CONTEXT = [
    "analytics_agent_adk/context.py",
    "db_agent_adk/context.py",
    "googlesearch_agent_adk/context.py",
    "brave_search_agent_adk/context.py"
]

base = "/Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/sub_agents"

for relative_path in FILES_AGENT:
    path = f"{base}/{relative_path}"
    with open(path, "r") as f:
        content = f.read()

    # Need to add auth_token: str = None to BOTH send_message and send_message_async if missing or just send_message.
    # We will do regex replacement
    
    # 1. Update send_message_async signature
    content = re.sub(
        r'(async def send_message_async\([^)]+session_id: str = "default")\)',
        r'\1, auth_token: str = None)',
        content
    )
    
    # analytics agent uses `token: str = None` instead of `project_id`. Let's just blindly add auth_token: str = None before `)`
    content = re.sub(
        r'(def send_message\([^)]+session_id: str = "default")\)',
        r'\1, auth_token: str = None)',
        content
    )
    
    # 2. Update send_message return
    # If there's `project_id`, we match up to session_id
    content = re.sub(
        r'(return asyncio\.run\(send_message_async\([^)]+session_id)\)',
        r'\1, auth_token)',
        content
    )

    with open(path, "w") as f:
        f.write(content)
    print(f"Patched {relative_path}")

for relative_path in FILES_CONTEXT:
    path = f"{base}/{relative_path}"
    with open(path, "r") as f:
        content = f.read()
    
    # Update signature
    content = re.sub(
        r'(async def _report_progress\(message: str, event_type: str = "INFO")\):',
        r'\1, icon: str = None, display_type: str = None):',
        content
    )

    # Some agents use `event_type, "..."` inside publisher.publish_event
    # We will try a simpler replace inside `publisher.publish_event` 
    content = re.sub(
        r'icon="[^"]+"',
        r'icon=icon or "💬"', 
        content
    )
    content = re.sub(
        r'(display_type="markdown" if mapped_type == "THOUGHT" else "console_log")',
        r'display_type or \1',
        content
    )

    with open(path, "w") as f:
        f.write(content)
    print(f"Patched {relative_path}")
