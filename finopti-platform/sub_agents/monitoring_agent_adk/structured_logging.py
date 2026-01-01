"""
Structured Logging Utility for FinOptiAgents Platform

This module provides structured JSON logging with request ID propagation
for all services in the platform.

Features:
- JSON formatted logs for easy parsing
- Request ID generation and propagation
- Contextual information (service, user, action)
- Integration with Loki/Grafana
"""

import logging
import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from contextvars import ContextVar
from functools import wraps

# Context variable for request ID (thread-safe)
request_id_context: ContextVar[Optional[str]] = ContextVar('request_id', default=None)

class StructuredLogger:
    """
    Structured logger that outputs JSON formatted logs.
    """
    
    def __init__(self, service_name: str, level=logging.INFO):
        """
        Initialize structured logger.
        
        Args:
            service_name: Name of the service (e.g., 'orchestrator', 'gcloud_agent')
            level: Logging level (default: INFO)
        """
        self.service_name = service_name
        self.logger = logging.getLogger(service_name)
        self.logger.setLevel(level)
        
        # Remove existing handlers
        self.logger.handlers = []
        
        # Create console handler
        handler = logging.StreamHandler()
        handler.setLevel(level)
        
        # Use custom formatter
        formatter = StructuredFormatter(service_name)
        handler.setFormatter(formatter)
        
        self.logger.addHandler(handler)
        self.logger.propagate = False
    
    def _log(self, level: str, message: str, **kwargs):
        """Internal method to create structured log entry"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "service": self.service_name,
            "message": message,
            "request_id": request_id_context.get(),
            **kwargs
        }
        
        # Remove None values
        log_entry = {k: v for k, v in log_entry.items() if v is not None}
        
        # Use appropriate logging level
        if level == "DEBUG":
            self.logger.debug(json.dumps(log_entry))
        elif level == "INFO":
            self.logger.info(json.dumps(log_entry))
        elif level == "WARNING":
            self.logger.warning(json.dumps(log_entry))
        elif level == "ERROR":
            self.logger.error(json.dumps(log_entry))
        elif level == "CRITICAL":
            self.logger.critical(json.dumps(log_entry))
    
    def debug(self, message: str, **kwargs):
        """Log debug message"""
        self._log("DEBUG", message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """Log info message"""
        self._log("INFO", message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning message"""
        self._log("WARNING", message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Log error message"""
        self._log("ERROR", message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """Log critical message"""
        self._log("CRITICAL", message, **kwargs)

class StructuredFormatter(logging.Formatter):
    """
    Custom formatter that outputs JSON.
    This is a fallback if logs aren't already in JSON format.
    """
    
    def __init__(self, service_name: str):
        super().__init__()
        self.service_name = service_name
    
    def format(self, record):
        # If the message is already JSON (from _log), return as is
        if record.msg.startswith('{'):
            return record.msg
        
        # Otherwise, create JSON structure
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "service": self.service_name,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_context.get()
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        return json.dumps({k: v for k, v in log_entry.items() if v is not None})

def generate_request_id() -> str:
    """Generate a unique request ID"""
    return str(uuid.uuid4())

def set_request_id(request_id: Optional[str] = None) -> str:
    """
    Set request ID in context.
    
    Args:
        request_id: Optional request ID. If None, generates a new one.
    
    Returns:
        The request ID that was set
    """
    if request_id is None:
        request_id = generate_request_id()
    request_id_context.set(request_id)
    return request_id

def get_request_id() -> Optional[str]:
    """Get current request ID from context"""
    return request_id_context.get()

def clear_request_id():
    """Clear request ID from context"""
    request_id_context.set(None)

def with_request_id(func):
    """
    Decorator to automatically handle request ID for Flask routes.
    
    Usage:
        @app.route('/api/endpoint')
        @with_request_id
        def my_endpoint():
            # request ID is automatically set
            logger.info("Processing request")
            return {"status": "ok"}
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        from flask import request
        
        # Get request ID from header or generate new one
        request_id = request.headers.get('X-Request-ID')
        set_request_id(request_id)
        
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            clear_request_id()
    
    return wrapper

def add_request_id_to_response(response):
    """
    Flask after_request handler to add request ID to response headers.
    
    Usage:
        app.after_request(add_request_id_to_response)
    """
    request_id = get_request_id()
    if request_id:
        response.headers['X-Request-ID'] = request_id
    return response

def log_request(logger: StructuredLogger):
    """
    Decorator to log HTTP requests with timing.
    
    Usage:
        @app.route('/api/endpoint')
        @log_request(logger)
        def my_endpoint():
            return {"status": "ok"}
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            from flask import request
            import time
            
            # Get request ID from header or generate
            request_id = request.headers.get('X-Request-ID')
            set_request_id(request_id)
            
            # Log request start
            start_time = time.time()
            logger.info(
                f"Request started: {request.method} {request.path}",
                method=request.method,
                path=request.path,
                user_email=request.headers.get('X-User-Email'),
                remote_addr=request.remote_addr
            )
            
            try:
                result = func(*args, **kwargs)
                
                # Log successful request
                duration_ms = (time.time() - start_time) * 1000
                status_code = getattr(result, 'status_code', 200) if hasattr(result, 'status_code') else 200
                
                logger.info(
                    f"Request completed: {request.method} {request.path}",
                    method=request.method,
                    path=request.path,
                    status_code=status_code,
                    duration_ms=round(duration_ms, 2),
                    user_email=request.headers.get('X-User-Email')
                )
                
                return result
                
            except Exception as e:
                # Log failed request
                duration_ms = (time.time() - start_time) * 1000
                logger.error(
                    f"Request failed: {request.method} {request.path}",
                    method=request.method,
                    path=request.path,
                    error=str(e),
                    duration_ms=round(duration_ms, 2),
                    user_email=request.headers.get('X-User-Email')
                )
                raise
            finally:
                clear_request_id()
        
        return wrapper
    return decorator

def propagate_request_id(headers: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add request ID to outgoing request headers.
    
    Usage:
        headers = {"Content-Type": "application/json"}
        headers = propagate_request_id(headers)
        response = requests.post(url, headers=headers, ...)
    
    Args:
        headers: Dictionary of headers
    
    Returns:
        Updated headers dictionary with X-Request-ID
    """
    request_id = get_request_id()
    if request_id:
        headers['X-Request-ID'] = request_id
    return headers
