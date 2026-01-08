
import os
import logging
import aiohttp
import asyncio
from typing import Dict, Any

logger = logging.getLogger("mats-workflow")

SRE_URL = os.getenv("SRE_AGENT_URL", "http://mats-sre-agent:8081")
INVESTIGATOR_URL = os.getenv("INVESTIGATOR_AGENT_URL", "http://mats-investigator-agent:8082")
ARCHITECT_URL = os.getenv("ARCHITECT_AGENT_URL", "http://mats-architect-agent:8083")

async def call_agent(url: str, message: str) -> str:
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(f"{url}/chat", json={"message": message}, timeout=300) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Agent at {url} failed: {resp.status} - {text}")
                data = await resp.json()
                return data.get("response", "")
        except Exception as e:
            logger.error(f"Failed to call agent {url}: {e}")
            raise

async def run_troubleshooting_workflow(
    project_id: str, 
    repo_owner: str, 
    repo_name: str, 
    branch: str,
    error_description: str
) -> Dict[str, Any]:
    
    stages = []
    
    # ---------------------------------------------------------
    # 1. SRE AGENT (Triage)
    # ---------------------------------------------------------
    logger.info("Starting Phase 1: SRE Triage")
    sre_prompt = f"""
    Analyze logs for GCP Project '{project_id}'.
    Context: {error_description}
    """
    sre_output = await call_agent(SRE_URL, sre_prompt)
    stages.append({"stage": "SRE", "output": sre_output})
    
    # ---------------------------------------------------------
    # 2. INVESTIGATOR AGENT (Code)
    # ---------------------------------------------------------
    logger.info("Starting Phase 2: Code Investigation")
    investigtor_prompt = f"""
    The SRE Agent has provided the following incident context:
    {sre_output}
    
    The Repository is: {repo_owner}/{repo_name} (Branch: {branch})
    
    Please investigate the code. Locate the error source, trace the logic, and explain *why* it failed.
    """
    investigator_output = await call_agent(INVESTIGATOR_URL, investigtor_prompt)
    stages.append({"stage": "Investigator", "output": investigator_output})
    
    # ---------------------------------------------------------
    # 3. ARCHITECT AGENT (RCA)
    # ---------------------------------------------------------
    logger.info("Starting Phase 3: Architect RCA")
    architect_prompt = f"""
    Here are the investigation reports:

    [SRE REPORT]
    {sre_output}

    [INVESTIGATOR REPORT]
    {investigator_output}

    Generate the final Root Cause Analysis document and the recommended code fix.
    """
    rca_doc = await call_agent(ARCHITECT_URL, architect_prompt)
    # stages.append({"stage": "Architect", "output": rca_doc}) # RCA is the final output
    
    return {
        "status": "success",
        "rca_markdown": rca_doc,
        "debug_stages": stages
    }
