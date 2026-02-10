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
if 'active_job_id' not in st.session_state:
    st.session_state.active_job_id = None
if 'job_status' not in st.session_state:
    st.session_state.job_status = None
if 'active_trace_id' not in st.session_state:
    st.session_state.active_trace_id = None
if 'active_session_id' not in st.session_state:
    st.session_state.active_session_id = None

# ... (Configuration)
APISIX_URL = "http://apisix:9080"
ORCHESTRATOR_ASK = f"{APISIX_URL}/orchestrator/ask"  # CHANGED: Use routing orchestrator, not direct MATS
MATS_JOBS = f"{APISIX_URL}/agent/mats/jobs"  # Keep for troubleshooting-specific flows if needed

# ... (Auth and Helpers)

import uuid
from opentelemetry import trace, propagate
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
# Simple OTel setup for UI (Trace Initiator)
# Note: For full OTLP export, we would add OTLPSpanExporter here.
# For now, we mainly need the ID generation logic.
trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)

def _generate_trace_id():
    """Generate a valid 32-char hex trace ID"""
    return uuid.uuid4().hex

def _get_trace_header(trace_id: str, span_id: str = None):
    """Create W3C traceparent header"""
    if not span_id:
        span_id = uuid.uuid4().hex[:16]
    return f"00-{trace_id}-{span_id}-01"

def start_job(prompt: str, trace_id: str = None, session_id: str = None) -> dict:
    """Send request to orchestrator for intelligent routing"""
    try:
        headers = oauth_helper.get_auth_headers()
        
        # 1. Trace Propagation Logic
        # ALWAYS generate a new trace_id for each request (don't reuse)
        trace_id = _generate_trace_id()
            
        span_id = uuid.uuid4().hex[:16]
        traceparent = _get_trace_header(trace_id, span_id)
        
        # Inject into headers
        headers["traceparent"] = traceparent
        # CRITICAL: Pass session ID for Phoenix session grouping
        if session_id:
            headers["X-Session-ID"] = session_id

        payload = {"prompt": prompt}
        
        # CHANGED: Use orchestrator/ask instead of direct MATS
        response = requests.post(
            ORCHESTRATOR_ASK,
            headers=headers,
            json=payload,
            timeout=1800  # 30 minutes for MATS investigations
        )
        
        if response.status_code == 200:
            data = response.json()
            # Store trace_id in response for UI tracking if needed
            data["trace_id"] = trace_id 
            return data
        else:
            return {"error": f"Failed to process request: {response.text}"}
            
    except Exception as e:
        return {"error": str(e)}

def poll_job(job_id: str, trace_id: str = None) -> dict:
    """Poll job status with consistent trace context"""
    try:
        headers = oauth_helper.get_auth_headers()
        
        # Verification: Continue the trace? Or new span? 
        # For polling, arguably a new span appearing under the same trace is best.
        if trace_id:
             # Create a new span ID for this poll request, linked to original trace
             headers["traceparent"] = _get_trace_header(trace_id)

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
    # Handle Resume via URL
    if "trace_id" in st.query_params and not st.session_state.active_trace_id:
        st.session_state.active_trace_id = st.query_params["trace_id"]
        st.toast(f"Resumed Trace: {st.session_state.active_trace_id}")

    # Display Session ID prominently at top
    col_session, col_new = st.columns([4, 1])
    with col_session:
        st.title("MATS Chat 💬")
        # Auto-generate session if not exists
        if not st.session_state.get('active_session_id'):
            st.session_state.active_session_id = _generate_trace_id()
        
        # Display Session ID prominently
        st.info(f"📋 **Session ID:** `{st.session_state.active_session_id}`")
        st.caption("Use this Session ID for troubleshooting in Phoenix: http://localhost:6006")
    
    with col_new:
        if st.button("➕ New Investigation", help="Start a fresh investigation with new session ID"):
            # Reset session ID to start new investigation session
            st.session_state.active_session_id = _generate_trace_id()
            st.session_state.active_job_id = None
            st.session_state.messages = []
            st.rerun()
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Chat input logic
    user_input = st.chat_input("Ask me to perform GCloud or Monitoring operations...")
    
    if st.session_state.pending_prompt:
        user_input = st.session_state.pending_prompt
        st.session_state.pending_prompt = None
    
    # Unified Logic: Determine if we have a job to run (New or Existing)
    current_job_id = None
    
    # Job Status Placeholders
    job_creation_status = st.empty()
    
    # Check if we have a pending message to process (from previous rerun)
    if "processing_message" in st.session_state:
        # Second pass: Process the message and get response
        processing_msg = st.session_state.processing_message
        del st.session_state.processing_message  # Clear flag immediately
        
        # Start/Resume Job
        with st.chat_message("assistant"):
             with job_creation_status.status("🚀 Initializing...", expanded=True) as status_ptr:
                 try:
                      # CRITICAL: Pass session_id (persistent) but NOT trace_id (per-request)
                      # start_job will generate a NEW trace_id for each request
                      response_data = start_job(
                          processing_msg, 
                          trace_id=None,  # Let start_job generate new trace_id
                          session_id=st.session_state.active_session_id  # Session persists across requests
                      )
                      
                      if "error" in response_data:
                          status_ptr.update(label="❌ Error", state="error")
                          error_msg = response_data["error"]
                          st.error(error_msg)
                          # Add error to message history
                          st.session_state.messages.append({"role": "assistant", "content": f"❌ Error: {error_msg}"})
                      else:
                          # SUCCESS - Display response immediately (synchronous)
                          status_ptr.update(label="✅ Complete", state="complete")
                          
                          response_text = ""
                          
                          # Check if this was routed to MATS (which returns status/error format)
                          if "status" in response_data:
                              # MATS response format
                              if response_data.get("status") == "MISROUTED":
                                  error_text = response_data.get("error", "Request was misrouted")
                                  st.error(error_text)
                                  response_text = f"❌ {error_text}"
                                  if "suggestion" in response_data:
                                      suggestion = response_data["suggestion"]
                                      st.info(suggestion)
                                      response_text += f"\n\n💡 {suggestion}"
                              else:
                                  st.write(response_data)
                                  response_text = str(response_data)
                          # Check for orchestrator routing response
                          elif "orchestrator" in response_data:
                              # Display routing info
                              orchestrator_info = response_data.get("orchestrator", {})
                              if "target_agent" in orchestrator_info:
                                  routing_info = f"🎯 Routed to: **{orchestrator_info['target_agent']}**"
                                  st.info(routing_info)
                                  response_text = routing_info + "\n\n"
                              
                              # Display agent response
                              if "response" in response_data:
                                  agent_resp = response_data["response"]
                                  st.write(agent_resp)
                                  response_text += str(agent_resp)
                              elif "data" in response_data:
                                  agent_resp = response_data["data"]
                                  st.write(agent_resp)
                                  response_text += str(agent_resp)
                              else:
                                  st.write(response_data)
                                  response_text += str(response_data)
                          else:
                              # Generic response
                              st.write(response_data)
                              response_text = str(response_data)
                          
                          # Add response to message history
                          st.session_state.messages.append({"role": "assistant", "content": response_text})
                          
                          # Clear pending prompt
                          st.session_state.pending_prompt = None
                          st.session_state.active_job_id = None  # No job polling needed
                          
                 except Exception as e:
                      status_ptr.update(label="❌ Error", state="error")
                      error_msg = str(e)
                      st.error(error_msg)
                      st.session_state.messages.append({"role": "assistant", "content": f"❌ Error: {error_msg}"})
    
    # 1. Handle New User Input
    elif user_input:
        is_waiting = (st.session_state.get('job_status') == "WAITING_FOR_USER")
        
        if st.session_state.active_job_id and not is_waiting:
             st.warning("⚠️ Another job is already running. Please wait.")
        else:
            # First pass: Add user message to history and trigger rerun for processing
            st.session_state.messages.append({"role": "user", "content": user_input})
            st.session_state.processing_message = user_input
            st.rerun()


# User profiles for simulated login
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
    # Auto-generate session ID on login
    if not st.session_state.get('active_session_id'):
        st.session_state.active_session_id = _generate_trace_id()
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
            timeout=1800
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
            "message": "Request timed out (execution took > 1800s). The agent is likely still working in the background."
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


