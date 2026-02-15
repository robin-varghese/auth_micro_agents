"""
Orchestrator ADK - Agent Registry Management
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Global Registry Cache
_AGENT_REGISTRY = None

def load_registry(registry_path: str = "master_agent_registry.json") -> List[Dict[str, Any]]:
    """Load the master agent registry, caching it in memory."""
    global _AGENT_REGISTRY
    if _AGENT_REGISTRY:
        return _AGENT_REGISTRY
        
    try:
        current_dir = Path(__file__).parent
        with open(current_dir / registry_path, 'r') as f:
            _AGENT_REGISTRY = json.load(f)
        return _AGENT_REGISTRY
    except Exception as e:
        # Fallback to empty if missing (should not happen in prod)
        logger.error(f"Error loading registry: {e}")
        return []

def get_agent_by_id(agent_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve agent definition by ID."""
    registry = load_registry()
    for agent in registry:
        if agent['agent_id'] == agent_id:
            return agent
    return None
