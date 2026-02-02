import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import config

def check_environment():
    print("--- Verifying GitHub Agent Environment ---")
    
    # Check 1: Import google.generativeai
    try:
        import google.generativeai as genai
        print("[PASS] google.generativeai imported successfully.")
    except ImportError as e:
        print(f"[FAIL] Could not import google.generativeai: {e}")
        return False
        
    # Check 2: API Key presence
    if hasattr(config, "GOOGLE_API_KEY") and config.GOOGLE_API_KEY:
        os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY
    
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("[WARN] GOOGLE_API_KEY not set. Skipping LLM generation test.")
        # We consider import success enough for "environment" check if no key provided
        return True
        
    print(f"[INFO] API Key found (starts with {api_key[:4]}...)")
    
    # Check 3: LLM Connectivity (if key exists)
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(config.FINOPTIAGENTS_LLM) # Use configured model
        print("[INFO] Attempting to generate content...")
        response = model.generate_content("Ping")
        print(f"[PASS] Generation successful. Response: {response.text.strip()}")
        return True
    except Exception as e:
        print(f"[FAIL] LLM Generation failed: {e}")
        return False

if __name__ == "__main__":
    success = check_environment()
    sys.exit(0 if success else 1)
