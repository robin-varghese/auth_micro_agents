import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
SUB_AGENTS_DIR = BASE_DIR / "sub_agents"
OUTPUT_FILE = BASE_DIR / "mats-agents/mats-orchestrator/agent_registry.json"

def generate_registry():
    registry = []
    
    if not SUB_AGENTS_DIR.exists():
        print(f"Error: Sub-agents directory not found at {SUB_AGENTS_DIR}")
        return

    print(f"Scanning agents in {SUB_AGENTS_DIR}...")
    
    for agent_dir in sorted(SUB_AGENTS_DIR.iterdir()):
        if agent_dir.is_dir():
            manifest_path = agent_dir / "manifest.json"
            if manifest_path.exists():
                try:
                    with open(manifest_path, "r") as f:
                        manifest = json.load(f)
                    
                    # Extract and transform fields
                    agent_entry = {
                        "agent_id": manifest.get("agent_id", agent_dir.name),
                        "name": manifest.get("display_name", agent_dir.name),
                        "capabilities": ", ".join(manifest.get("capabilities", [])) if isinstance(manifest.get("capabilities"), list) else manifest.get("capabilities", ""),
                        "anti_patterns": " ".join(manifest.get("anti_patterns", [])) if isinstance(manifest.get("anti_patterns"), list) else manifest.get("anti_patterns", ""),
                    }
                    
                    # Add guardrail if present
                    if "guardrail" in manifest:
                        agent_entry["guardrail"] = manifest["guardrail"]
                        
                    registry.append(agent_entry)
                    print(f"  - Added {agent_entry['name']} ({agent_entry['agent_id']})")
                    
                except Exception as e:
                    print(f"  - Error reading {manifest_path}: {e}")
            else:
                print(f"  - Skipping {agent_dir.name} (No manifest.json)")

    # Ensure output directory exists
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    with open(OUTPUT_FILE, "w") as f:
        json.dump(registry, f, indent=4)
        
    print(f"\nRegistry generated successfully at {OUTPUT_FILE}")
    print(f"Total agents: {len(registry)}")

if __name__ == "__main__":
    generate_registry()
