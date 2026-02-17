import json
from pathlib import Path

MANIFEST_PATH = Path(__file__).parent / "manifest.json"
INSTRUCTIONS_PATH = Path(__file__).parent / "instructions.json"

def load_instructions():
    if INSTRUCTIONS_PATH.exists():
        with open(INSTRUCTIONS_PATH, "r") as f:
            data = json.load(f)
            return data.get("instruction", "You represent the agent.")
    return "You represent the agent."

def load_manifest():
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, "r") as f:
            return json.load(f)
    return {}

AGENT_INSTRUCTIONS = load_instructions()
MANIFEST = load_manifest()
AGENT_NAME = MANIFEST.get("agent_id", "iam_verification_specialist")
AGENT_DESCRIPTION = MANIFEST.get("description", "IAM Agent")
