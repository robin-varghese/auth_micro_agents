import os
from pathlib import Path

def update_file(filepath):
    print(f"Checking {filepath}...")
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        target = '    try:\n        response = requests.post(url, json={"prompt": PROMPT}, timeout=60)'
        replacement = '    headers = {}\n    token = os.getenv("GOOGLE_OAUTH_ACCESS_TOKEN")\n    if token:\n        headers["Authorization"] = f"Bearer {token}"\n        print("Using OAuth Token in request.")\n\n    try:\n        response = requests.post(url, json={"prompt": PROMPT}, headers=headers, timeout=60)'
        
        if target in content:
            new_content = content.replace(target, replacement)
            with open(filepath, 'w') as f:
                f.write(new_content)
            print(f"✅ Updated {filepath}")
        elif "Authorization" in content:
            print(f"ℹ️ Already updated {filepath}")
        else:
            print(f"⚠️ Target string not found in {filepath}")
            
    except Exception as e:
        print(f"❌ Error updating {filepath}: {e}")

def main():
    root = Path("/Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform")
    
    # 1. Sub-Agents
    sub_agents = list(root.glob("sub_agents/*/verify_agent.py"))
    
    # 2. Mats Agents
    mats_agents = list(root.glob("mats-agents/*/verify_agent.py"))
    
    all_files = sub_agents + mats_agents
    
    print(f"Found {len(all_files)} files to check.")
    for f in all_files:
        update_file(f)

if __name__ == "__main__":
    main()
