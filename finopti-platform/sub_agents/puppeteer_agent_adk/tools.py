"""
Puppeteer Agent Tools
"""
import logging
import base64
from pathlib import Path
from typing import Dict, Any
from mcp_client import ensure_mcp

logger = logging.getLogger(__name__)

async def puppeteer_navigate(url: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("puppeteer_navigate", {"url": url})

async def puppeteer_screenshot(name: str = "screenshot", width: int = 1200, height: int = 800, filename: str = None) -> Dict[str, Any]:
    client = await ensure_mcp()
    result = await client.call_tool("puppeteer_screenshot", {"name": name, "width": width, "height": height})
    
    # Check for image data and save to shared volume
    if result.get("image"):
        try:
            # Default filename if not provided
            if not filename:
                filename = f"{name}.png"
            
            # Ensure filename ends with .png
            if not filename.endswith(".png"):
                filename += ".png"
                
            # Define path in shared volume
            save_path = Path("/projects") / filename
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Decode and write
            image_bytes = base64.b64decode(result["image"])
            with open(save_path, "wb") as f:
                f.write(image_bytes)
                
            logger.info(f"Saved screenshot to {save_path}")
            result["result"] += f"\n\n[System] Screenshot saved to shared volume at: {save_path}"
            
            # Store filename for orchestrator chaining
            client.last_filename = filename
            
            # Clear huge base64 string from result
            result["image"] = "[Saved to file]"
            
        except Exception as e:
            logger.error(f"Failed to save screenshot: {e}")
            result["result"] += f"\n\n[System] Failed to save screenshot file: {e}"

    return result

async def puppeteer_click(selector: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("puppeteer_click", {"selector": selector})

async def puppeteer_fill(selector: str, value: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("puppeteer_fill", {"selector": selector, "value": value})

async def puppeteer_evaluate(script: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("puppeteer_evaluate", {"script": script})

async def puppeteer_hover(selector: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("puppeteer_hover", {"selector": selector})
