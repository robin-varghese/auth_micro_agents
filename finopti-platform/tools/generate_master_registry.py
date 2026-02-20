import json
import os
import glob
from pathlib import Path

def generate_master_registry():
    """
    Scans sub_agents/ and mats-agents/ for manifest.json files
    and aggregates them into a master_agent_registry.json
    """
    base_dir = Path(__file__).parent.parent
    registry = []
    
    # 1. Scan sub_agents
    sub_agents_pattern = base_dir / "sub_agents" / "*" / "manifest.json"
    
    # 2. Scan mats-agents
    mats_agents_pattern = base_dir / "mats-agents" / "*" / "manifest.json"
    
    files = list(glob.glob(str(sub_agents_pattern))) + list(glob.glob(str(mats_agents_pattern)))
    
    print(f"Found {len(files)} manifest files.")
    
    for manifest_path in files:
        try:
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
                
            # Basic validation
            if "agent_id" not in manifest or "keywords" not in manifest:
                print(f"Skipping {manifest_path}: Missing agent_id or keywords")
                continue
                
            # Add path context
            manifest["_source_path"] = str(Path(manifest_path).parent.relative_to(base_dir))
            
            # [FIX] Normalize name/display_name for consistency (planner.py expects 'name')
            if "name" not in manifest and "display_name" in manifest:
                manifest["name"] = manifest["display_name"]
            elif "display_name" not in manifest and "name" in manifest:
                manifest["display_name"] = manifest["name"]
            elif "name" not in manifest and "display_name" not in manifest:
                manifest["name"] = manifest["agent_id"]
                manifest["display_name"] = manifest["agent_id"]
                
            registry.append(manifest)
            print(f"Loaded: {manifest['agent_id']}")
            
        except Exception as e:
            print(f"Error processing {manifest_path}: {e}")
            
    # Write master registry
    output_path = base_dir / "mats-agents" / "mats-orchestrator" / "agent_registry.json"
    
    with open(output_path, 'w') as f:
        json.dump(registry, f, indent=2)
        
    print(f"Successfully generated master registry at {output_path} with {len(registry)} agents.")

if __name__ == "__main__":
    generate_master_registry()
