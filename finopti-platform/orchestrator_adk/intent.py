"""
Orchestrator ADK - Intent Detection Logic
"""
import re
import os
import logging
from typing import Dict
from registry import load_registry

logger = logging.getLogger(__name__)

def detect_intent(prompt: str) -> str:
    """
    Dynamic intent detection based on Master Agent Registry keywords.
    
    Priority:
    1. Context information updates → route to Orchestrator for state update
    2. Simple CRUD operations → route to appropriate agent (bypass MATS)
    3. Troubleshooting requests → route to MATS
    4. Keyword-based scoring → find best matching agent
    5. Default fallback → gcloud
    """
    registry = load_registry()
    prompt_lower = prompt.lower()
    
    # 0. Detect simple CRUD operations (highest priority - bypass MATS)
    simple_operations = [
        r'\blist\s+(all|my|the)?\s*',
        r'\bshow\s+(all|my|the)?\s*',
        r'\bget\s+(all|my|the)?\s*',
        r'\bcreate\s+a?\s*',
        r'\bdelete\s+a?\s*',
        r'\bupdate\s+a?\s*',
        r'\bdescribe\s+',
        r'\bfind\s+',
    ]
    
    is_simple_operation = any(re.search(pattern, prompt_lower) for pattern in simple_operations)
    
    # 0.5. Detect context-gathering responses (e.g., "The project is...", "Repo: ...")
    context_patterns = [
        r'\bproject is\s+',
        r'\bproject id\s+(is|:)?\s*',
        r'\benvironment\s+(is|:)?\s*',
        r'\bproduction\b',
        r'\bstaging\b',
        r'\bapplication\s+(name\s+)?(is|:)?\s*',
        r'\brepo\s*(url|is|:)?\s*',
        r'\bgithub\s*pat\b',
        r'\bbranch\s*(is|:)?\s*',
    ]
    
    is_context_update = any(re.search(pattern, prompt_lower) for pattern in context_patterns)
    if is_context_update:
        logger.info(f"Routing to Orchestrator (Interactive Context Update): match found")
        return "finopti_orchestrator"

    # 1. Check for explicit MATS triggers (only if NOT a simple operation)
    if not is_simple_operation:
        # MATS triggers - require clear troubleshooting intent with multi-word phrases
        mats_triggers = [
            "troubleshoot",
            "root cause",
            "rca",
            "why is",
            "why did",
            "why does",
            "what caused",
            "find the bug",
            "find the issue",
            "investigation",
            "investigate",
            "analyze",
            "investigate the failure",
            "investigate the error",
            "investigate the crash",
            "investigate the issue",
            "investigate the problem",
            "diagnose the",
            "debug the",
            "fix the issue",
            "fix the bug",
            "fix the problem",
            "apply the fix",
            "remediate",
            "apply solution",
            "not running",
            "is down",
            "stopped working",
            "failing",
            "exception",
            "crashed",
            "timeout",
            "latency",
            "slow",
            "infinite loop",
            "deadlock",
            "out of memory"
        ]
        
        if any(trigger in prompt_lower for trigger in mats_triggers):
            logger.info(f"Routing to MATS: matched keyword trigger")
            return "mats-orchestrator"

        # Regex triggers for robustness (catch typos like 'runnig')
        mats_regex = [
            r'\bnot\s+run[a-z]*\b',     # not running, runnig
            r'\bnot\s+work[a-z]*\b',    # not working
            r'\bnot\s+start[a-z]*\b',   # not starting
            r'\bfailed?\b',             # fail, failed
            r'\bcrashed?\b',            # crash, crashed
            r'\berror(s)?\b',           # error, errors (careful, might be too broad but safer for RCA)
            r'\bexception(s)?\b',       # exception
        ]

        if any(re.search(p, prompt_lower) for p in mats_regex):
            logger.info(f"Routing to MATS: matched regex trigger")
            return "mats-orchestrator"
    
    # 2. Score based on keywords in registry
    scores = {}
    
    for agent in registry:
        agent_id = agent['agent_id']
        keywords = agent.get('keywords', [])
        score = 0
        
        for k in keywords:
            k_lower = k.lower()
            # Use word boundary matching for better accuracy
            if len(k_lower) <= 3:
                # Short keywords need exact word match
                if re.search(r'\b' + re.escape(k_lower) + r'\b', prompt_lower):
                    score += 2
            else:
                # Longer keywords can match as substring
                if k_lower in prompt_lower:
                    score += 1
                    # Bonus for multi-word concepts ("cloud run", "google cloud")
                    if ' ' in k_lower:
                        score += 2
                        
        scores[agent_id] = score
    
    # Debug logging if enabled
    if os.getenv("DEBUG_ROUTING", "false").lower() == "true":
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
        logger.info(f"Routing scores for '{prompt[:50]}...': {sorted_scores}")
    
    # Find winner - require minimum score
    if scores:
        best_agent_id = max(scores, key=scores.get)
        if scores[best_agent_id] >= 1:  # At least 1 keyword match required
            logger.info(f"Routing to {best_agent_id} (score: {scores[best_agent_id]})")
            return best_agent_id
    
    # Default fallback
    logger.info(f"Routing to default: gcloud_infrastructure_specialist")
    return "gcloud_infrastructure_specialist"
