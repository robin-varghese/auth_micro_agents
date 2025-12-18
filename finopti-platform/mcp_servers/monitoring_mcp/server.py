"""
Monitoring MCP Server - Mock Implementation

This is a mock Model Context Protocol server for Monitoring/Observability tools.
It simulates monitoring queries for the prototype.

In production, this would be replaced with the actual MCP server
that queries real monitoring systems (Cloud Monitoring, Prometheus, etc.).
"""

from flask import Flask, request, jsonify
import logging
import random

app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "monitoring_mcp"}), 200

@app.route('/', methods=['POST'])
def handle_jsonrpc():
    """
    Handle JSON-RPC 2.0 requests for Monitoring operations.
    
    Expected format:
        {
            "jsonrpc": "2.0",
            "method": "check_cpu" | "check_memory" | "query_logs" | "get_metrics",
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
        if method == 'check_cpu':
            result = check_cpu(params)
        elif method == 'check_memory':
            result = check_memory(params)
        elif method == 'query_logs':
            result = query_logs(params)
        elif method == 'get_metrics':
            result = get_metrics(params)
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

def check_cpu(params: dict) -> dict:
    """
    Mock CPU usage check.
    
    Args:
        params: {
            "resource": str,
            "period": str
        }
    
    Returns:
        CPU usage data
    """
    resource = params.get('resource', 'compute')
    period = params.get('period', '5m')
    
    # Generate mock CPU usage
    cpu_usage = random.randint(30, 90)
    
    logger.info(f"Mock: Checked CPU usage for {resource}: {cpu_usage}%")
    
    return {
        "success": True,
        "metric": "cpu_utilization",
        "resource": resource,
        "period": period,
        "value": cpu_usage,
        "unit": "percent",
        "message": f"CPU Usage is {cpu_usage}%",
        "timestamp": "2025-12-18T18:00:00Z"
    }

def check_memory(params: dict) -> dict:
    """
    Mock memory usage check.
    
    Args:
        params: {
            "resource": str,
            "period": str
        }
    
    Returns:
        Memory usage data
    """
    resource = params.get('resource', 'compute')
    period = params.get('period', '5m')
    
    # Generate mock memory usage
    memory_usage = random.randint(40, 85)
    
    logger.info(f"Mock: Checked Memory usage for {resource}: {memory_usage}%")
    
    return {
        "success": True,
        "metric": "memory_utilization",
        "resource": resource,
        "period": period,
        "value": memory_usage,
        "unit": "percent",
        "message": f"Memory Usage is {memory_usage}%",
        "timestamp": "2025-12-18T18:00:00Z"
    }

def query_logs(params: dict) -> dict:
    """
    Mock log query.
    
    Args:
        params: {
            "filter": str,
            "limit": int
        }
    
    Returns:
        Log entries
    """
    log_filter = params.get('filter', 'severity>=INFO')
    limit = params.get('limit', 10)
    
    logger.info(f"Mock: Querying logs with filter={log_filter}, limit={limit}")
    
    # Generate mock log entries
    mock_logs = [
        {
            "timestamp": "2025-12-18T17:55:00Z",
            "severity": "ERROR",
            "message": "Connection timeout to database",
            "resource": "app-server-1"
        },
        {
            "timestamp": "2025-12-18T17:56:30Z",
            "severity": "WARNING",
            "message": "High memory usage detected",
            "resource": "app-server-2"
        },
        {
            "timestamp": "2025-12-18T17:58:15Z",
            "severity": "INFO",
            "message": "Application started successfully",
            "resource": "app-server-3"
        }
    ]
    
    return {
        "success": True,
        "filter": log_filter,
        "count": len(mock_logs),
        "logs": mock_logs[:limit],
        "operation": "query_logs"
    }

def get_metrics(params: dict) -> dict:
    """
    Mock metrics retrieval.
    
    Args:
        params: {
            "metric_type": str
        }
    
    Returns:
        Metric data
    """
    metric_type = params.get('metric_type', 'cpu_utilization')
    
    logger.info(f"Mock: Getting metrics for type={metric_type}")
    
    # Generate mock time series data
    mock_metrics = {
        "metric_type": metric_type,
        "data_points": [
            {"timestamp": "2025-12-18T17:50:00Z", "value": 45.2},
            {"timestamp": "2025-12-18T17:55:00Z", "value": 52.8},
            {"timestamp": "2025-12-18T18:00:00Z", "value": 48.5}
        ],
        "unit": "percent"
    }
    
    return {
        "success": True,
        "metrics": mock_metrics,
        "operation": "get_metrics"
    }

if __name__ == '__main__':
    logger.info("Starting Monitoring MCP Server on port 6002")
    app.run(host='0.0.0.0', port=6002, debug=False)
