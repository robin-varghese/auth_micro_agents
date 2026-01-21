import os
import re
from pathlib import Path

def update_file(filepath):
    print(f"Checking {filepath}...")
    try:
        with open(filepath, 'r') as f:
            content = f.read()
            
        if "headers[\"Authorization\"]" in content:
            print(f"ℹ️ Already updated {filepath}")
            return

        # Regex to find the requests.post call
        # It looks for: response = requests.post(url, json={"prompt": PROMPT}, timeout=...)
        # We want to capture the timeout value to preserve it
        pattern = r'(response\s*=\s*requests\.post\(url,\s*json=\{"prompt":\s*PROMPT\},\s*timeout=(\d+)\))'
        
        match = re.search(pattern, content)
        if match:
            original_line = match.group(1)
            timeout_val = match.group(2)
            
            replacement = f'''headers = {{}}
    token = os.getenv("GOOGLE_OAUTH_ACCESS_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {{token}}"
        print("Using OAuth Token in request.")

    try:
        response = requests.post(url, json={{"prompt": PROMPT}}, headers=headers, timeout={timeout_val})'''
            
            # Use replace on the exact string matched to avoid regex complexity in sub
            new_content = content.replace("    try:\n        " + original_line, replacement)
            
            # Fallback if indentation didn't match perfectly (e.g. if I missed the 'try:' context in regex)
            # Actually, let's just replace the line inside the try block
            
            # Better approach: find the specific line and replace it + insert header logic before 'try:'
            
            # Find the 'try:' line
            idx_try = content.find("    try:")
            if idx_try != -1:
                # Insert header logic before try
                header_logic = '    headers = {}\n    token = os.getenv("GOOGLE_OAUTH_ACCESS_TOKEN")\n    if token:\n        headers["Authorization"] = f"Bearer {token}"\n        print("Using OAuth Token in request.")\n\n'
                
                # Replace the requests.post line
                new_content = content[:idx_try] + header_logic + content[idx_try:]
                
                # Now add headers=headers to the requests.post call
                # We use regex sub for this specific line now
                new_content = re.sub(
                    r'(requests\.post\(url,\s*json=\{"prompt":\s*PROMPT\},)(\s*timeout=\d+\))',
                    r'\1 headers=headers,\2',
                    new_content
                )
                
                with open(filepath, 'w') as f:
                    f.write(new_content)
                print(f"✅ Updated {filepath}")
            else:
                 print(f"⚠️ 'try:' block not found in {filepath}")
        else:
            print(f"⚠️ Target pattern not found in {filepath}")
            
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
