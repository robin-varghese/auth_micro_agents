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
import oauth_helper

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
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_email' not in st.session_state:
    st.session_state.user_email = None
if 'user_name' not in st.session_state:
    st.session_state.user_name = None
if 'id_token' not in st.session_state:
    st.session_state.id_token = None
if 'auth_method' not in st.session_state:
    st.session_state.auth_method = None  # 'oauth' or 'simulated'
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'pending_prompt' not in st.session_state:
    st.session_state.pending_prompt = None

def login_simulated(user_email: str):
    """Simulate user login (development mode)"""
    st.session_state.authenticated = True
    st.session_state.user_email = user_email
    st.session_state.user_name = AVAILABLE_USERS[user_email]['name']
    st.session_state.auth_method = 'simulated'
    st.session_state.messages = []
    st.success(f"Logged in as {AVAILABLE_USERS[user_email]['name']} (Simulated)")

def logout():
    """Logout user"""
    oauth_helper.logout()
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
        # Get auth headers (includes Bearer token if OAuth)
        headers = oauth_helper.get_auth_headers()
        
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
    
    # Extract agent response text
    if "response" in data:
        resp = data["response"]
        if isinstance(resp, dict):
             if "response" in resp:
                 return resp["response"]
             elif "message" in resp:
                 return resp["message"]
    
    # Fallback to result
    if "result" in data:
        result = data["result"]
        if isinstance(result, dict):
            return result.get("message", str(result))
        return str(result)
        
    return "No response text found."

# Handle OAuth callback first
if oauth_helper.is_oauth_enabled():
    if oauth_helper.handle_oauth_callback():
        st.rerun()

# Sidebar - Login
with st.sidebar:
    st.title("🤖 FinOptiAgents")
    st.markdown("---")
    
    # Show OAuth status
    if oauth_helper.is_oauth_enabled():
        st.caption(oauth_helper.get_oauth_status())
    
    if not st.session_state.authenticated:
        st.subheader("🔐 Login")
        
        # Tab for OAuth vs Simulated auth
        if oauth_helper.is_oauth_enabled():
            auth_tab1, auth_tab2 = st.tabs(["Google OAuth", "Simulated"])
            
            with auth_tab1:
                st.caption("Real Google Authentication")
                oauth_url = oauth_helper.get_oauth_login_url()
                st.markdown(
                    f'<a href="{oauth_url}" target="_self">'
                    '<button style="width:100%; background:#4285f4; color:white; '
                    'border:none; padding:10px; border-radius:4px; cursor:pointer;">'
                    '🔐 Login with Google</button></a>',
                    unsafe_allow_html=True
                )
                st.caption("Redirects to Google for authentication")
            
            with auth_tab2:
                st.caption("Development Mode (No Auth)")
                selected_user = st.selectbox(
                    "Select User:",
                    options=list(AVAILABLE_USERS.keys()),
                    format_func=lambda x: f"{AVAILABLE_USERS[x]['name']} ({x})",
                    key="simulated_user"
                )
                
                if selected_user:
                    user_info = AVAILABLE_USERS[selected_user]
                    st.info(f"**Role:** {user_info['role']}\n\n{user_info['description']}")
                
                if st.button("🚀 Login (Simulated)", use_container_width=True):
                    login_simulated(selected_user)
                    st.rerun()
        else:
            # OAuth disabled - simulated auth only
            st.caption("⚠️ OAuth Not Configured - Using Simulated Auth")
            st.markdown("To enable OAuth, configure:")
            st.code("GOOGLE_OAUTH_CLIENT_ID\nGOOGLE_OAUTH_CLIENT_SECRET")
            
            selected_user = st.selectbox(
                "Select User:",
                options=list(AVAILABLE_USERS.keys()),
                format_func=lambda x: f"{AVAILABLE_USERS[x]['name']} ({x})"
            )
            
            if selected_user:
                user_info = AVAILABLE_USERS[selected_user]
                st.info(f"**Role:** {user_info['role']}\n\n{user_info['description']}")
            
            if st.button("🚀 Login", use_container_width=True):
                login_simulated(selected_user)
                st.rerun()
    
    else:
        st.success("✅ Logged In")
        
        # Show auth method
        auth_method = st.session_state.get('auth_method', 'unknown')
        if auth_method == 'oauth':
            st.caption("🔐 Google OAuth")
        elif auth_method == 'simulated':
            st.caption("⚙️ Simulated Auth (Dev Mode)")
        
        user_name = st.session_state.get('user_name', st.session_state.user_email)
        st.write(f"**Name:** {user_name}")
        st.write(f"**Email:** {st.session_state.user_email}")
        
        # Show role if available
        if st.session_state.user_email in AVAILABLE_USERS:
            st.write(f"**Role:** {AVAILABLE_USERS[st.session_state.user_email]['role']}")
        
        st.markdown("---")
        
        if st.button("🚪 Logout", use_container_width=True):
            logout()
            st.rerun()
    
    # Help section & Shortcuts
    st.markdown("---")
    st.subheader("⚡ Sample Prompts")
    
    def set_prompt(txt):
        st.session_state.pending_prompt = txt
    
    if st.button("List GCloud VMs", use_container_width=True):
        set_prompt("List all VMs in my google cloud project vector-search-poc")
        st.rerun()
        
    if st.button("List Recent Operations", use_container_width=True):
         set_prompt("list last 10 operations in my google cloud project vector-search-poc")
         st.rerun()

    if st.button("List GitHub Repos", use_container_width=True):
        set_prompt("list all GitHub code repos in my account https://github.com/robin-varghese")
        st.rerun()

    if st.button("List GCS Buckets", use_container_width=True):
        set_prompt("list all google cloud storage buckets in my google cloud project vector-search-poc")
        st.rerun()
        
    st.markdown("---")
    st.caption("FinOptiAgents Platform v1.0")

# Main content
if not st.session_state.authenticated:
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
    
    # Chat input logic
    user_input = st.chat_input("Ask me to perform GCloud or Monitoring operations...")
    
    # Check for pending prompt from shortcuts
    if st.session_state.pending_prompt:
        user_input = st.session_state.pending_prompt
        st.session_state.pending_prompt = None
    
    if user_input:
        # Add user message to chat
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
        
        # Send to orchestrator with simple loading state
        with st.status("🤔 Thinking...", expanded=True) as status:
            st.write("🔄 Orchestrating request...")
            response = send_message(user_input)
            
            if response.get("success"):
                status.update(label="✅ Response received!", state="complete", expanded=False)
            else:
                status.update(label="❌ Request failed", state="error", expanded=True)
        
        # Format and display assistant response
        assistant_message = format_response(response)
        st.session_state.messages.append({"role": "assistant", "content": assistant_message})
        with st.chat_message("assistant"):
            st.markdown(assistant_message)
