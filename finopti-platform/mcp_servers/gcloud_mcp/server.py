"""
GCloud MCP Server - Mock Implementation

This is a mock Model Context Protocol server for GCloud tools.
It simulates actual GCloud operations for the prototype.

In production, this would be replaced with the actual MCP server
that executes real gcloud commands.
"""

from flask import Flask, request, jsonify
import logging
import json

app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Mock VM data
mock_vms = []

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "gcloud_mcp"}), 200

@app.route('/', methods=['POST'])
def handle_jsonrpc():
    """
    Handle JSON-RPC 2.0 requests for GCloud operations.
    
    Expected format:
        {
            "jsonrpc": "2.0",
            "method": "create_vm" | "delete_vm" | "list_vms",
            "params": {...},
            "id": 1
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": "Parse error"},
                "id": None
            }), 400
        
        method = data.get('method')
        params = data.get('params', {})
        request_id = data.get('id')
        
        logger.info(f"Received JSON-RPC request: method={method}, params={params}")
        
        # Route to appropriate handler
        if method == 'create_vm':
            result = create_vm(params)
        elif method == 'delete_vm':
            result = delete_vm(params)
        elif method == 'list_vms':
            result = list_vms(params)
        else:
            return jsonify({
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Method not found: {method}"},
                "id": request_id
            }), 400
        
        response = {
            "jsonrpc": "2.0",
            "result": result,
            "id": request_id
        }
        
        logger.info(f"Sending response: {response}")
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Error handling JSON-RPC request: {e}", exc_info=True)
        return jsonify({
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
            "id": data.get('id') if data else None
        }), 500

def create_vm(params: dict) -> dict:
    """
    Mock VM creation.
    
    Args:
        params: {
            "instance_name": str,
            "zone": str,
            "machine_type": str (optional)
        }
    
    Returns:
        Success message with VM details
    """
    instance_name = params.get('instance_name', 'demo-instance')
    zone = params.get('zone', 'us-central1-a')
    machine_type = params.get('machine_type', 'e2-medium')
    
    vm = {
        "name": instance_name,
        "zone": zone,
        "machine_type": machine_type,
        "status": "RUNNING",
        "created_at": "2025-12-18T18:00:00Z"
    }
    
    mock_vms.append(vm)
    
    logger.info(f"Mock: Created VM {instance_name} in zone {zone}")
    
    return {
        "success": True,
        "message": f"VM Instance '{instance_name}' created successfully in zone {zone}",
        "instance": vm,
        "operation": "create_vm"
    }

def delete_vm(params: dict) -> dict:
    """
    Mock VM deletion.
    
    Args:
        params: {
            "instance_name": str,
            "zone": str
        }
    
    Returns:
        Success message
    """
    instance_name = params.get('instance_name', 'demo-instance')
    zone = params.get('zone', 'us-central1-a')
    
    # Remove from mock VMs if exists
    global mock_vms
    mock_vms = [vm for vm in mock_vms if vm['name'] != instance_name]
    
    logger.info(f"Mock: Deleted VM {instance_name} from zone {zone}")
    
    return {
        "success": True,
        "message": f"VM Instance '{instance_name}' deleted successfully from zone {zone}",
        "operation": "delete_vm"
    }

def list_vms(params: dict) -> dict:
    """
    Mock VM listing.
    
    Args:
        params: {
            "zone": str (optional)
        }
    
    Returns:
        List of VMs
    """
    zone = params.get('zone', 'all')
    
    logger.info(f"Mock: Listing VMs in zone {zone}")
    
    # Return mock VMs or default example
    vms = mock_vms if mock_vms else [
        {
            "name": "example-vm-1",
            "zone": "us-central1-a",
            "machine_type": "e2-medium",
            "status": "RUNNING"
        },
        {
            "name": "example-vm-2",
            "zone": "us-east1-b",
            "machine_type": "n1-standard-1",
            "status": "STOPPED"
        }
    ]
    
    return {
        "success": True,
        "count": len(vms),
        "instances": vms,
        "operation": "list_vms"
    }

if __name__ == '__main__':
    logger.info("Starting GCloud MCP Server on port 6001")
    app.run(host='0.0.0.0', port=6001, debug=False)
