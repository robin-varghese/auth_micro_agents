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
    page_title="MATS Platform",
    page_icon="assets/mats_logo.jpg",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for styling
st.markdown("""
    <style>
        /* Sidebar background to white */
        [data-testid="stSidebar"] {
            background-color: #FFFFFF;
        }
        /* Main content background to light gray */
        .stApp {
            background-color: #F8F9FA;
        }
    </style>
""", unsafe_allow_html=True)

import time

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

# ... (Configuration)
APISIX_URL = "http://apisix:9080"
ORCHESTRATOR_JOBS = f"{APISIX_URL}/agent/mats/jobs"

# ... (Auth and Helpers)

def start_job(prompt: str) -> dict:
    """Start an async troubleshooting job"""
    try:
        headers = oauth_helper.get_auth_headers()
        payload = {"prompt": prompt}
        
        response = requests.post(
            ORCHESTRATOR_JOBS,
            headers=headers,
            json=payload,
            timeout=10
        )
        
        if response.status_code == 202:
            return response.json() # {"job_id": "...", "status": "RUNNING"}
        else:
            return {"error": f"Failed to start job: {response.text}"}
            
    except Exception as e:
        return {"error": str(e)}

def poll_job(job_id: str) -> dict:
    """Poll job status"""
    try:
        headers = oauth_helper.get_auth_headers()
        response = requests.get(
            f"{ORCHESTRATOR_JOBS}/{job_id}",
            headers=headers,
            timeout=5
        )
        if response.status_code == 200:
            return response.json()
        return {"error": "Failed to poll"}
    except:
        return {"error": "Poll error"}

# ... (Sidebar)

# Main Content
if not st.session_state.authenticated:
    # ... (Login Page)
    pass
else:
    st.title("MATS Chat 💬")
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Chat input logic
    user_input = st.chat_input("Ask me to perform GCloud or Monitoring operations...")
    
    if st.session_state.pending_prompt:
        user_input = st.session_state.pending_prompt
        st.session_state.pending_prompt = None
    
    if user_input:
        # Add user message to chat
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
        
        # Async Interaction Loop
        with st.chat_message("assistant"):
            status_container = st.status("🚀 Initializing...", expanded=True)
            console_container = st.empty()
            plan_container = st.empty()
            
            # 1. Start Job
            job_data = start_job(user_input)
            
            if "error" in job_data:
                status_container.update(label="❌ Failed to start", state="error")
                st.error(job_data["error"])
            else:
                job_id = job_data["job_id"]
                status_container.update(label="🔄 MATS Active", state="running")
                
                # 2. Poll Loop
                final_result = None
                processed_events = set()
                
                start_time = time.time()
                while True:
                    # Timeout safety
                    if time.time() - start_time > 600:
                        status_container.update(label="❌ Timeout", state="error")
                        break
                        
                    status_data = poll_job(job_id)
                    current_status = status_data.get("status", "UNKNOWN")
                    
                    # Update Events
                    events = status_data.get("events", [])
                    
                    # Render Plan if found
                    for evt in events:
                        if evt["type"] == "PLAN" and "plan_rendered" not in st.session_state:
                            plan_container.markdown(evt["message"])
                            
                    # Render Console Log items (Latest 20)
                    console_text = ""
                    for evt in events[-10:]:
                        icon = "ℹ️"
                        if evt["type"] == "TOOL_USE": icon = "🛠️"
                        elif evt["type"] == "OBSERVATION": icon = "✅"
                        elif evt["type"] == "THOUGHT": icon = "🧠"
                        elif evt["type"] == "ERROR": icon = "❌"
                        elif evt["type"] == "PLAN": icon = "📋"
                        
                        source = evt.get("source", "system").replace("mats-", "").replace("-agent", "").upper()
                        console_text += f"{icon} **[{source}]** {evt['message']}\n\n"
                        
                    console_container.caption(console_text)
                    
                    if current_status in ["COMPLETED", "FAILED", "PARTIAL"]:
                        final_result = status_data.get("result")
                        if current_status == "COMPLETED":
                            status_container.update(label="✅ Complete", state="complete", expanded=False)
                        else:
                            status_container.update(label=f"⚠️ {current_status}", state="error", expanded=False)
                        break
                        
                    time.sleep(2)
                
                # 3. Render Final Response
                if final_result:
                    # Parse result for nicer display
                    response_msg = ""
                    if isinstance(final_result, dict):
                         response_msg = final_result.get("response") or final_result.get("message") or str(final_result)
                    else:
                         response_msg = str(final_result)
                         
                    st.markdown(response_msg)
                    st.session_state.messages.append({"role": "assistant", "content": response_msg})
                else:
                     st.error("No final result received.")
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
        
        response = requests.post(
            ORCHESTRATOR_ENDPOINT,
            headers=headers,
            json=payload,
            timeout=600
        )
        
        if response.status_code == 200:
            try:
                data = response.json()
                return {
                    "success": True,
                    "data": data
                }
            except ValueError:
                return {
                    "success": False,
                    "error": "Invalid Response",
                    "message": f"Server returned 200 OK but invalid JSON: {response.text[:200]}"
                }

        elif response.status_code == 403:
            try:
                msg = response.json().get("message", "Access denied")
            except ValueError:
                msg = response.text
                
            return {
                "success": False,
                "error": "Authorization Error",
                "message": msg
            }
            
        elif response.status_code == 504:
            return {
                "success": False,
                "error": "Gateway Timeout",
                "message": (
                    "The request took too long to process (timeout > 10m). "
                    "The agent is likely still working in the background. "
                    "Please check back later or check the 'rca-reports-mats' bucket directly."
                )
            }
            
        else:
            try:
                msg = response.json().get("message", "Unknown error")
            except ValueError:
                msg = f"Raw response: {response.text[:200]}"
                
            return {
                "success": False,
                "error": f"HTTP {response.status_code}",
                "message": msg
            }
    
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "Timeout",
            "message": "Request timed out (execution took > 600s). The agent is likely still working in the background."
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
    st.image("assets/mats_logo.jpg", width=250)
    # st.title("🤖 MATS")
    st.markdown("---")
    
    # Show OAuth status
    # Removed as per user request

    
    if not st.session_state.authenticated:
        # Tab for OAuth vs Simulated auth
        if oauth_helper.is_oauth_enabled():
            auth_tab1, auth_tab2 = st.tabs(["Google OAuth", "Simulated"])
            
            with auth_tab1:
                oauth_url = oauth_helper.get_oauth_login_url()
                st.markdown(
                    f'<a href="{oauth_url}" target="_self">'
                    '<button style="width:100%; background:#4285f4; color:white; '
                    'border:none; padding:10px; border-radius:4px; cursor:pointer;">'
                    '🔐 Login with Google</button></a>',
                    unsafe_allow_html=True
                )
            
            with auth_tab2:
                selected_user = st.selectbox(
                    "Select User:",
                    options=list(AVAILABLE_USERS.keys()),
                    format_func=lambda x: f"{AVAILABLE_USERS[x]['name']} ({x})",
                    key="simulated_user"
                )
                
                if st.button("🚀 Login (Simulated)", use_container_width=True):
                    login_simulated(selected_user)
                    st.rerun()
        else:
             # OAuth disabled - simulated auth only
            selected_user = st.selectbox(
                "Select User:",
                options=list(AVAILABLE_USERS.keys()),
                format_func=lambda x: f"{AVAILABLE_USERS[x]['name']}",
                label_visibility="collapsed"
            )
            
            if st.button("🚀 Login", use_container_width=True):
                login_simulated(selected_user)
                st.rerun()
    
    else:
        # Logged In state - kept minimal
        user_name = st.session_state.get('user_name', st.session_state.user_email)
        st.success(f"Hi, {user_name}")

        if st.button("🚪 Logout", use_container_width=True):
            logout()
            st.rerun()

    # Help section & Shortcuts (Only show when authenticated)
    if st.session_state.authenticated:
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

        st.markdown("**New Capabilities**")

        if st.button("Google Search", use_container_width=True):
            set_prompt("Search google for 'latest Google Cloud Run features'")
            st.rerun()

        if st.button("Code Execution", use_container_width=True):
            set_prompt("Calculate the 100th Fibonacci number using Python")
            st.rerun()

        if st.button("Filesystem List", use_container_width=True):
            set_prompt("List files in the current directory")
            st.rerun()

        if st.button("Google Analytics Report", use_container_width=True):
            set_prompt("Run a report for active users in the last 7 days")
            st.rerun()

        if st.button("Puppeteer Screenshot", use_container_width=True):
            set_prompt("Take a screenshot of https://www.google.com")
            st.rerun()

        if st.button("Sequential Planning", use_container_width=True):
            set_prompt("Plan a 3-day itinerary for a trip to Tokyo step-by-step")
            st.rerun()

        st.markdown("**Troubleshooting (MATS)**")
        
        if st.button("Troubleshoot Cloud Run", use_container_width=True):
            set_prompt("I have hosted one cloud run service in my gcp project vector-search-poc. name:calculator-app Region: us-central1 URL: https://calculator-app-912533822336.us-central1.run.app can you troubleshoot this application for any problem. ")
            st.rerun()

        if st.button("Debug Deployment", use_container_width=True):
            set_prompt("Debug the failed deployment in project 'vector-search-poc'. Why did it fail?")
            st.rerun()

        st.markdown("**Infrastructure**")

        if st.button("List Cloud Run Services", use_container_width=True):
            set_prompt("List all Cloud Run services in us-central1")
            st.rerun()

        if st.button("Check Monitoring Metrics", use_container_width=True):
            set_prompt("Show CPU utilization for the last hour")
            st.rerun()

        st.markdown("**Data & Storage**")

        if st.button("Query Database Schema", use_container_width=True):
            set_prompt("Show me the schema for the 'users' table in the database")
            st.rerun()

        if st.button("List Storage Objects", use_container_width=True):
            set_prompt("List files in the 'finopti-assets' bucket")
            st.rerun()

        
    st.markdown("---")
    st.caption("MATS Platform v1.0")


