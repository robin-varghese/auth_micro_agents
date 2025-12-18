"""
FinOptiAgents - Streamlit UI

This is the frontend interface for the FinOptiAgents platform.
It simulates Google Auth (for prototype) and provides a chat interface
for interacting with the agent system.

Request Flow:
1. User selects their identity (simulated login)
2. User enters a prompt in the chat
3. UI sends POST to http://apisix:9080/orchestrator/ask with X-User-Email header
4. Response is displayed in the chat interface
"""

import streamlit as st
import requests
import json
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="FinOptiAgents Platform",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Configuration
APISIX_URL = "http://apisix:9080"
ORCHESTRATOR_ENDPOINT = f"{APISIX_URL}/orchestrator/ask"

# Available users (simulated Google Auth)
AVAILABLE_USERS = {
    "admin@cloudroaster.com": {
        "name": "Admin User",
        "role": "gcloud_admin",
        "description": "Full access to GCloud operations"
    },
    "monitoring@cloudroaster.com": {
        "name": "Monitoring User",
        "role": "observability_admin",
        "description": "Access to monitoring and observability"
    },
    "robin@cloudroaster.com": {
        "name": "Robin (Developer)",
        "role": "developer",
        "description": "Limited access for testing"
    }
}

# Initialize session state
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_email' not in st.session_state:
    st.session_state.user_email = None
if 'messages' not in st.session_state:
    st.session_state.messages = []

def login(user_email: str):
    """Simulate user login"""
    st.session_state.logged_in = True
    st.session_state.user_email = user_email
    st.session_state.messages = []
    st.success(f"Logged in as {AVAILABLE_USERS[user_email]['name']}")

def logout():
    """Logout user"""
    st.session_state.logged_in = False
    st.session_state.user_email = None
    st.session_state.messages = []
    st.info("Logged out successfully")

def send_message(prompt: str) -> dict:
    """
    Send message to orchestrator via APISIX.
    
    Args:
        prompt: User's message
        
    Returns:
        Response from the agent system
    """
    try:
        headers = {
            "X-User-Email": st.session_state.user_email,
            "Content-Type": "application/json"
        }
        payload = {
            "prompt": prompt
        }
        
        with st.spinner("Processing your request..."):
            response = requests.post(
                ORCHESTRATOR_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=60
            )
        
        if response.status_code == 200:
            return {
                "success": True,
                "data": response.json()
            }
        elif response.status_code == 403:
            return {
                "success": False,
                "error": "Authorization Error",
                "message": response.json().get("message", "Access denied")
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}",
                "message": response.json().get("message", "Unknown error")
            }
    
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "Timeout",
            "message": "Request timed out after 60 seconds"
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": "Connection Error",
            "message": "Could not connect to APISIX. Ensure all services are running."
        }
    except Exception as e:
        return {
            "success": False,
            "error": "Error",
            "message": str(e)
        }

def format_response(response_data: dict) -> str:
    """Format the agent response for display"""
    if not response_data.get("success", False):
        return f"❌ **{response_data.get('error', 'Error')}**\n\n{response_data.get('message', 'Unknown error')}"
    
    data = response_data.get("data", {})
    
    # Check if it's an error response from orchestrator
    if data.get("error", False):
        return f"❌ **Error**\n\n{data.get('message', 'Unknown error')}"
    
    # Format successful agent response
    lines = []
    
    # Orchestrator info
    if "orchestrator" in data:
        orch = data["orchestrator"]
        lines.append(f"**🎯 Target Agent:** {orch.get('target_agent', 'unknown')}")
        lines.append(f"**✅ Authorization:** {orch.get('authorization', 'granted')}")
        lines.append("")
    
    # Agent info
    if "agent" in data:
        lines.append(f"**🤖 Agent:** {data['agent']}")
    if "action" in data:
        lines.append(f"**⚙️ Action:** {data['action']}")
    
    # Result
    if "result" in data:
        result = data["result"]
        
        if isinstance(result, dict):
            if result.get("success"):
                lines.append(f"\n**✅ Result:** {result.get('message', 'Success')}")
                
                # Show additional details if available
                if "instance" in result:
                    inst = result["instance"]
                    lines.append(f"\n**Instance Details:**")
                    lines.append(f"- Name: {inst.get('name')}")
                    lines.append(f"- Zone: {inst.get('zone')}")
                    lines.append(f"- Machine Type: {inst.get('machine_type')}")
                    lines.append(f"- Status: {inst.get('status')}")
                
                if "instances" in result:
                    instances = result["instances"]
                    lines.append(f"\n**Found {result.get('count', 0)} instances:**")
                    for inst in instances[:5]:  # Show first 5
                        lines.append(f"- {inst.get('name')} ({inst.get('zone')}) - {inst.get('status')}")
                
                if "metric" in result:
                    lines.append(f"\n**📊 {result.get('message', '')}**")
                    lines.append(f"- Metric: {result.get('metric')}")
                    lines.append(f"- Value: {result.get('value')}{result.get('unit', '')}")
                
                if "logs" in result:
                    logs = result["logs"]
                    lines.append(f"\n**📝 Found {result.get('count', 0)} log entries:**")
                    for log in logs[:3]:  # Show first 3
                        lines.append(f"- [{log.get('severity')}] {log.get('message')} ({log.get('resource')})")
            else:
                lines.append(f"\n❌ {result.get('message', 'Operation failed')}")
        else:
            lines.append(f"\n**Result:** {result}")
    
    return "\n".join(lines)

# Sidebar - Login
with st.sidebar:
    st.title("🤖 FinOptiAgents")
    st.markdown("---")
    
    if not st.session_state.logged_in:
        st.subheader("🔐 Login")
        st.caption("Simulated Google Auth for Prototype")
        
        selected_user = st.selectbox(
            "Select User:",
            options=list(AVAILABLE_USERS.keys()),
            format_func=lambda x: f"{AVAILABLE_USERS[x]['name']} ({x})"
        )
        
        if selected_user:
            user_info = AVAILABLE_USERS[selected_user]
            st.info(f"**Role:** {user_info['role']}\n\n{user_info['description']}")
        
        if st.button("🚀 Login", use_container_width=True):
            login(selected_user)
            st.rerun()
    
    else:
        st.success("✅ Logged In")
        user_info = AVAILABLE_USERS[st.session_state.user_email]
        st.write(f"**Name:** {user_info['name']}")
        st.write(f"**Email:** {st.session_state.user_email}")
        st.write(f"**Role:** {user_info['role']}")
        
        st.markdown("---")
        
        if st.button("🚪 Logout", use_container_width=True):
            logout()
            st.rerun()
    
    # Help section
    st.markdown("---")
    st.subheader("💡 Example Prompts")
    st.markdown("""
    **GCloud Operations:**
    - Create a VM instance
    - List all VMs
    - Delete a VM
    
    **Monitoring:**
    - Check CPU usage
    - Check memory usage
    - Query error logs
    - Get metrics
    """)
    
    st.markdown("---")
    st.caption("FinOptiAgents Platform v1.0")
    st.caption("Built with Streamlit, APISIX, and OPA")

# Main content
if not st.session_state.logged_in:
    st.title("Welcome to FinOptiAgents 🤖")
    st.markdown("""
    ### FinOps Agentic Platform with Hub-and-Spoke Architecture
    
    This platform demonstrates a secure, scalable architecture for AI agents with:
    
    - **🎯 Orchestrator Agent**: Central hub for routing requests
    - **🔐 OPA Authorization**: Role-based access control
    - **🌐 Apache APISIX**: API Gateway for observability and routing
    - **🤖 Sub-Agents**: Specialized agents for GCloud and Monitoring
    - **🔧 MCP Servers**: Model Context Protocol servers for tools
    
    **👈 Please login from the sidebar to get started.**
    """)
    
    # Architecture diagram
    st.markdown("### Architecture Overview")
    st.image("https://via.placeholder.com/800x400/2E3440/88C0D0?text=User+→+APISIX+→+Orchestrator+→+OPA+→+Sub-Agents+→+MCP+Servers", 
             caption="Hub-and-Spoke Architecture")

else:
    st.title("FinOptiAgents Chat 💬")
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Chat input
    if prompt := st.chat_input("Ask me to perform GCloud or Monitoring operations..."):
        # Add user message to chat
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Send to orchestrator and get response
        response = send_message(prompt)
        
        # Format and display assistant response
        assistant_message = format_response(response)
        st.session_state.messages.append({"role": "assistant", "content": assistant_message})
        with st.chat_message("assistant"):
            st.markdown(assistant_message)
        
        # Show raw response in expander for debugging
        with st.expander("🔍 View Raw Response"):
            st.json(response)
