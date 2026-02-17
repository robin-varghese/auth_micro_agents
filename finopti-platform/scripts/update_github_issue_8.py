import os
import sys
import json
import time
import logging
import threading
import queue
import subprocess
from google.cloud import secretmanager

# Configure logging to stdout
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Constants
PROJECT_ID = "vector-search-poc"
SECRET_ID = "github-personal-access-token"
REPO_OWNER = "robin-varghese"
REPO_NAME = "auth_micro_agents"
MCP_IMAGE = "finopti-github-mcp"

def get_secret(project_id, secret_id, version_id="latest"):
    """
    Access the payload for the given secret version if one exists.
    """
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logger.error(f"Failed to access secret {secret_id}: {e}")
        return None

class GitHubMCPClientSync:
    """Synchronous Client for connecting to GitHub MCP server via Docker Stdio"""
    
    def __init__(self, token: str):
        self.image = MCP_IMAGE
        self.github_token = token
        self.process = None
        self.request_id = 0
        self.stdout_queue = queue.Queue()
        self.stderr_queue = queue.Queue()
        self.running = False

    def _enqueue_output(self, pipe, q, name):
        """Read lines from pipe and put into queue."""
        try:
            for line in iter(pipe.readline, b''):
                q.put(line)
            pipe.close()
        except Exception as e:
            logger.error(f"Error reading from {name}: {e}")

    def connect(self):
        cmd = [
            "docker", "run", "-i", "--rm", 
            "-e", f"GITHUB_PERSONAL_ACCESS_TOKEN={self.github_token}",
            "-e", "GITHUB_TOOLSETS=all",
            self.image
        ]
        
        logger.info(f"Starting GitHub MCP Sync with image {self.image}...")
        
        # Merge stderr into stdout to simplify reading and avoid deadlocks
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, 
            bufsize=0 # unbuffered binary
        )
        self.running = True
        
        # Single thread for reading all output
        self.t_out = threading.Thread(target=self._enqueue_output, args=(self.process.stdout, self.stdout_queue, "stdout"))
        self.t_out.daemon = True
        self.t_out.start()
        
        logger.info("Process started. Performing handshake...")
        self._handshake()

    def _read_json_line(self, timeout=10):
        start = time.time()
        while time.time() - start < timeout:
            try:
                line = self.stdout_queue.get(timeout=0.1)
                line_str = line.decode().strip()
                if not line_str: continue # empty line
                
                # If line looks like a log (doesn't start with {), log it and continue
                if not line_str.startswith("{"):
                    logger.info(f"MCP LOG: {line_str}")
                    continue
                
                return json.loads(line_str)
            except queue.Empty:
                continue # loop again
            except json.JSONDecodeError:
                logger.warning(f"JSON Decode Error: {line_str}")
                continue
        
        raise TimeoutError("Timed out waiting for JSON response")

    def _handshake(self):
        self._send_json({
            "jsonrpc": "2.0", "method": "initialize", "id": 0,
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "github-agent", "version": "1.0"}}
        })
        
        while True:
            msg = self._read_json_line(timeout=10)
            if msg.get("id") == 0: break
            
        self._send_json({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        logger.info("Handshake Complete.")

    def _send_json(self, payload):
        if not self.process or self.process.poll() is not None:
            raise RuntimeError("Process is not running")
        
        # Send bytes + newline
        data = (json.dumps(payload) + "\n").encode()
        self.process.stdin.write(data)
        self.process.stdin.flush()

    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        self.request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
            "id": self.request_id
        }
        self._send_json(payload)
        
        while True:
            msg = self._read_json_line(timeout=50) # Increased timeout
            if msg.get("id") == self.request_id:
                if "error" in msg: return {"error": msg["error"]}
                result = msg.get("result", {})
                content = result.get("content", [])
                output_text = ""
                for c in content:
                    if c["type"] == "text": output_text += c["text"]
                
                try: 
                    return json.loads(output_text) if output_text.strip().startswith("{") or output_text.strip().startswith("[") else output_text
                except:
                    return output_text

    def close(self):
        self.running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except: 
                self.process.kill()

    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

def close_issue(client, issue_number: int, comment: str):
    logger.info(f"Closing issue #{issue_number}...")
    try:
        # 1. Add comment
        client.call_tool("add_issue_comment", {"owner": REPO_OWNER, "repo": REPO_NAME, "issue_number": issue_number, "body": comment})
        # 2. Close issue
        client.call_tool("update_issue", {"owner": REPO_OWNER, "repo": REPO_NAME, "issue_number": issue_number, "state": "closed"})
        logger.info(f"Issue #{issue_number} closed.")
    except Exception as e:
        logger.error(f"Failed to update issue #{issue_number}: {e}")

def main():
    token = get_secret(PROJECT_ID, SECRET_ID)
    if not token:
        logger.error("Could not retrieve GitHub PAT. Exiting.")
        return

    try:
        with GitHubMCPClientSync(token) as client:
            comment = """Completed Phase 3 Tasks:
- Fixed GitHub Agent Integration (stdio deadlock)
- Standardized RCA Template to JSON format (`RCA-Template-V1.json`)
- Created JSON Remediation Template (`Remediation-Template-V1.json`)
- Migrated templates to GCS (`gs://rca-reports-mats/rca-templates/` and `remediation-templates/`)
- Updated Orchestrator and Remediation Agents to fetch templates from GCS (with local fallback)."""
            
            close_issue(client, 8, comment)
                
    except Exception as e:
        logger.error(f"Script failed: {e}")

if __name__ == "__main__":
    main()
