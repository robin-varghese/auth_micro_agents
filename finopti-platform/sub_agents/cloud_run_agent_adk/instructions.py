"""
Cloud Run Agent Instructions & Config
"""
import json
from pathlib import Path

MANIFEST_PATH = Path(__file__).parent / "manifest.json"
INSTRUCTIONS_PATH = Path(__file__).parent / "instructions.json"

def load_manifest():
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, "r") as f:
            return json.load(f)
    return {}

def load_instructions():
    if INSTRUCTIONS_PATH.exists():
        with open(INSTRUCTIONS_PATH, "r") as f:
            data = json.load(f)
            return data.get("instruction", "You are a Cloud Run expert.")
    return "You are a Cloud Run expert."

AGENT_DESCRIPTION = load_manifest().get("description", "Google Cloud Run specialist.")
AGENT_INSTRUCTIONS = load_instructions()
AGENT_NAME = load_manifest().get("agent_id", "cloud_run_specialist")
