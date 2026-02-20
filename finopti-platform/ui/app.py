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
import threading
import uuid
import time
import concurrent.futures
import queue

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
# Initialize session state for persistent session ID
if 'active_session_id' not in st.session_state:
    st.session_state.active_session_id = _generate_trace_id()



# ... (Configuration)
APISIX_URL = "http://apisix:9080"
ORCHESTRATOR_ASK = f"{APISIX_URL}/orchestrator/ask"  # CHANGED: Use routing orchestrator, not direct MATS
MATS_JOBS = f"{APISIX_URL}/agent/mats/jobs"  # Keep for troubleshooting-specific flows if needed
ORCHESTRATOR_JOBS = f"{APISIX_URL}/orchestrator/jobs" # Assuming this endpoint exists for polling

# ... (Auth and Helpers)



def start_job(prompt: str, user_email: str, trace_id: str = None, session_id: str = None, stream_ready_event: threading.Event = None) -> dict:
    """Send request to orchestrator for intelligent routing"""
    try:
        # SYNC: Wait for Redis Stream connection to be ready before firing the request
        if stream_ready_event:
            # Wait up to 5 seconds for the stream to connect
            stream_ready_event.wait(timeout=5)

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
        
        # CRITICAL FIX: Pass identity to Orchestrator
        if user_email:
            headers["X-User-Email"] = user_email

        payload = {"prompt": prompt}
        
        # CHANGED: Use orchestrator/ask instead of direct MATS
        response = requests.post(
            ORCHESTRATOR_ASK,
            headers=headers,
            json=payload,
            timeout=1800  # 30 minutes for MATS investigations
        )
        
        # CHANGED: Accept 202 (Accepted/Async) as success
        if response.status_code in [200, 202]:
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

def poll_until_complete(job_id: str, trace_id: str = None) -> dict:
    """Poll job status until terminal state"""
    # Max poll time: 30 minutes
    end_time = time.time() + 1800
    while time.time() < end_time:
        result = poll_job(job_id, trace_id)
        status = result.get("status")
        
        if status in ["COMPLETED", "SUCCESS", "FAILURE", "MISROUTED", "WAITING_FOR_USER", "SKIPPED", "PARTIAL"]:
            return result
        
        if "error" in result and "Job not found" not in result["error"]:
             # If error interacting with API, return it
             return result
             
        time.sleep(2)
        
    return {"error": "Polling timed out"}

# Redis Gateway Client
REDIS_GATEWAY_URL = "http://finopti-redis-gateway:8000"

def init_redis_channel(user_id: str, session_id: str):
    """
    Task 1: Call Redis Gateway to initialize the session channel.
    This ensures the backend is ready to receive messages for this session.
    """
    try:
        payload = {
            "user_id": user_id,
            "session_id": session_id
        }
        response = requests.post(f"{REDIS_GATEWAY_URL}/session/init", json=payload, timeout=2)
        if response.status_code == 200:
            data = response.json()
            # Optional: Store channel name if needed, but the convention is deterministic
            return data
        else:
            print(f"Warning: Failed to init Redis channel: {response.text}")
    except Exception as e:
        print(f"Warning: Redis Gateway unavailable: {e}")

# --- UI Rendering Logic ---
def render_event(event_data, status_container):
    """
    Renders a Redis event based on ui_rendering specification.
    """
    try:
        ui = event_data.get("ui_rendering", {})
        payload = event_data.get("payload", {})
        header = event_data.get("header", {})
        
        display_type = ui.get("display_type", "markdown")
        icon = ui.get("icon", "🤖")
        message = payload.get("message", "")
        agent_role = header.get("agent_role", "Agent")
        
        # 1. Toast Notification
        if display_type == "toast":
            st.toast(message, icon=icon)
            
        # 2. Step Progress (Spinner Update)
        elif display_type == "step_progress":
            status_container.update(label=f"{icon} {message}", state="running")
            # Optionally write to expanded status to keep history
            status_container.write(f"{icon} {message}")
            
        # 3. Markdown (Chat Bubble)
        elif display_type == "markdown":
            with st.chat_message(agent_role, avatar=icon):
                st.markdown(message)
            
            if event_data.get("type") in ["THOUGHT", "ARTIFACT"]:
                 st.session_state.messages.append({
                     "role": "assistant", 
                     "content": message,
                     "avatar": icon,
                     "agent_role": agent_role
                 })

        # 4. Code Block
        elif display_type == "code_block":
            with st.chat_message(agent_role, avatar=icon):
                st.code(message, language=payload.get("metadata", {}).get("language", "json"))

        # 5. Console Log
        elif display_type == "console_log":
            label = "Logs"
            if icon == "👁️":
                label = "Data Extract (Manual Analysis)"
            elif icon == "🛠️":
                label = "Tool Execution Details"
            
            with st.expander(f"{icon} {label}"):
                 st.text(message)

        # 6. Alerts
        elif display_type == "alert":
            st.error(message, icon=icon)
        elif display_type == "alert_success":
            st.success(message, icon=icon)

    except Exception as e:
        print(f"Render Error: {e}")


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
        # Task 1: Init Redis Channel on login
        init_redis_channel(user_email, st.session_state.active_session_id)
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

def set_prompt(txt: str):
    """Set the pending prompt in session state"""
    st.session_state.pending_prompt = txt

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

        st.markdown("**Remediation**")

        if st.button("Apply Remediation (RCA)", use_container_width=True, help="Apply fix using an RCA document or Automation Spec"):
            template = (
                "Apply remediation for the following RCA Automation Spec:\n"
                "gcp project: vector-search-poc\n"
                "service name:calculator-app\n"
                "Region: us-central1\n"
                "TARGET_URL: https://calculator-app-912533822336.us-central1.run.app\n"
                "RCA Document: https://storage.cloud.google.com/rca-reports-mats/MATS-RCA-calculator-app-20260210.md\n" 
                "Automation Spec: https://storage.cloud.google.com/rca-reports-mats/MATS-RCA-calculator-app-20260210.md\n"
            )
            set_prompt(template)
            st.rerun()
        

        
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


# Main Content - Execution
if not st.session_state.authenticated:
    # Login prompt (handled by sidebar for now, or could be a main page welcome)
    st.info("Please login from the sidebar to continue.")
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
            # Task 1: Init Redis Channel on first load
            user_id = st.session_state.get('user_email', 'anonymous')
            init_redis_channel(user_id, st.session_state.active_session_id)
        
        # Display Session ID prominently
        st.info(f"📋 **Session ID:** `{st.session_state.active_session_id}`")
        st.caption("Use this Session ID for troubleshooting in Phoenix: http://localhost:6006")
    
    with col_new:
        if st.button("➕ New Investigation", help="Start a fresh investigation with new session ID"):
            # Reset session ID to start new investigation session
            st.session_state.active_session_id = _generate_trace_id()
            # Task 1: Init Redis Channel on manual reset
            user_id = st.session_state.get('user_email', 'anonymous')
            init_redis_channel(user_id, st.session_state.active_session_id)
            
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
        
    # ... (Start/Resume Job)
        with st.chat_message("assistant"):
             status_container = st.status("🚀 Initiating...", expanded=True)
             
             user_id = st.session_state.get('user_email', 'anonymous')
             session_id = st.session_state.active_session_id
             
             # RACE CONDITION FIX: Event to signal when stream is connected
             stream_ready = threading.Event()

             executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
             
             # Phase 1: Submit the Job
             future = executor.submit(
                 start_job, 
                 processing_msg, 
                 user_id,
                 trace_id=None, 
                 session_id=session_id,
                 stream_ready_event=stream_ready
             )
             
             # State to track if we have transitioned to polling
             is_polling = False
             
             # Queue for stream events
             event_queue = queue.Queue()
             stop_stream = threading.Event()
             
             def consume_stream(url):
                 try:
                     with requests.get(url, stream=True, timeout=1800) as stream_resp:
                         if stream_resp.status_code == 200:
                             stream_ready.set()
                             
                         for line in stream_resp.iter_lines():
                             if stop_stream.is_set():
                                 break
                             if line:
                                 event_queue.put(line)
                 except Exception as e:
                     print(f"Stream error: {e}")
                 finally:
                     stream_ready.set() # Ensure we don't block start_job
             
             try:
                 # CONSUME STREAM (Task 3: Streaming)
                 stream_url = f"{REDIS_GATEWAY_URL}/stream/{user_id}/{session_id}"
                 
                 # Start background thread for stream
                 stream_thread = threading.Thread(target=consume_stream, args=(stream_url,), daemon=True)
                 stream_thread.start()
                 
                 # Main Event Loop
                 while True:
                     # 1. Check if the current task (Submission OR Polling) is done
                     if future.done():
                         result = future.result()
                         
                         if not is_polling:
                             # Submission phase complete. Check if we need to poll.
                             if result.get("status") in ["RUNNING", "RESUMED", "PENDING"]:
                                 job_id = result.get("job_id")
                                 if job_id:
                                     # Transition to Polling Phase
                                     is_polling = True
                                     st.session_state.active_job_id = job_id
                                     # Submit Polling Task
                                     future = executor.submit(poll_until_complete, job_id)
                                     continue # Continue loop
                             else:
                                 # Sync result or Error - WE ARE DONE
                                 stop_stream.set()
                                 break
                         else:
                             # Polling phase complete. We have the final result. - WE ARE DONE
                             stop_stream.set()
                             break
                     
                     # 2. Process Events from Queue (Non-blocking)
                     try:
                         # Wait for 0.1s to allow UI to be responsive and check future.done()
                         line = event_queue.get(timeout=0.1)
                         line_text = line.decode('utf-8')
                         if line_text.startswith("data: "):
                             try:
                                 event_data = json.loads(line_text[6:])
                                 render_event(event_data, status_container)
                             except json.JSONDecodeError:
                                 pass
                     except queue.Empty:
                         continue
                 
             except Exception as e:
                 # If stream fails (e.g. timeout), just ignore and wait for result
                 print(f"Main loop error: {e}")
                 stop_stream.set()
                 stream_ready.set()
             
             # Get Final Result
             try:
                 response_data = future.result()
                 
                 if "error" in response_data:
                      status_container.update(label="❌ Error", state="error")
                      st.error(response_data["error"])
                      st.session_state.messages.append({"role": "assistant", "content": f"❌ Error: {response_data['error']}"})
                 else:
                      status_container.update(label="✅ Complete", state="complete")
                      
                      # ... (Format Response Logic) ...
                      response_text = ""
                      should_display = True

                      # Check if this was routed to MATS
                      if "status" in response_data:
                           if response_data.get("status") == "MISROUTED":
                               error_text = response_data.get("error", "Request was misrouted")
                               st.error(error_text)
                               response_text = f"❌ {error_text}"
                               if "suggestion" in response_data:
                                   suggestion = response_data["suggestion"]
                                   st.info(suggestion)
                                   response_text += f"\n\n💡 {suggestion}"
                           else:
                               # Check for 'response' field first (standard)
                               if "response" in response_data:
                                   response_text = str(response_data["response"])
                               elif "result" in response_data:
                                    # Handle nested result from JobManager
                                    res = response_data["result"]
                                    if isinstance(res, dict) and "response" in res:
                                        response_text = res["response"]
                                    else:
                                        response_text = str(res)
                               else:
                                   response_text = str(response_data)
                                   
                      elif "orchestrator" in response_data:
                           # Display routing info
                           orchestrator_info = response_data.get("orchestrator", {})
                           if "target_agent" in orchestrator_info:
                               routing_info = f"🎯 Routed to: **{orchestrator_info['target_agent']}**"
                               response_text = routing_info + "\n\n"
                           
                           # Display agent response
                           if "response" in response_data:
                               agent_resp = response_data["response"]
                               response_text += str(agent_resp)
                           elif "data" in response_data:
                               agent_resp = response_data["data"]
                               response_text += str(agent_resp)
                           else:
                               response_text += str(response_data)
                      else:
                           response_text = str(response_data)
                      
                      # DEDUPLICATION CHECK
                      last_msg = st.session_state.messages[-1] if st.session_state.messages else {}
                      if last_msg.get("content") == response_text or (response_text and response_text in last_msg.get("content", "")):
                           should_display = False
                      
                      if should_display:
                           st.write(response_text)
                           st.session_state.messages.append({"role": "assistant", "content": response_text})
                      
                      st.session_state.pending_prompt = None
                      st.session_state.active_job_id = None
                      
             except Exception as e:
                  status_container.update(label="❌ Error", state="error")
                  st.error(str(e))
    
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
