import json
import os
from pathlib import Path

# Extracted from orchestrator_adk/agent.py
KEYWORD_MAPPING = {
    "gcloud_agent_adk": {
        "agent_id": "gcloud_infrastructure_specialist",
        "keywords": ['vm', 'instance', 'create', 'delete', 'compute', 'gcp', 'cloud', 'provision', 'machine', 'disk', 'network', 'firewall', 'operations', 'project', 'region', 'zone', 'google cloud']
    },
    "github_agent_adk": {
        "agent_id": "github_repository_specialist",
        "keywords": ['github', 'repo', 'repository', 'git', 'pull request', 'pr', 'issue', 'code', 'commit', 'push', 'pull']
    },
    "storage_agent_adk": {
         "agent_id": "gcs_storage_specialist",
         "keywords": ['bucket', 'object', 'blob', 'gcs', 'upload', 'download', 'storage']
    },
    "db_agent_adk": {
        "agent_id": "sql_database_specialist",
        "keywords": ['database', 'sql', 'query', 'table', 'postgres', 'postgresql', 'schema', 'select', 'insert', 'bigquery', 'bq', 'history']
    },
    "monitoring_agent_adk": {
        "agent_id": "monitoring_observability_specialist",
        "keywords": ['cpu', 'memory', 'logs', 'metrics', 'monitor', 'alert', 'usage', 'check', 'performance', 'latency', 'error', 'log', 'trace', 'observability']
    },
    "cloud_run_agent_adk": {
        "agent_id": "cloud_run_specialist",
        "keywords": ['cloud run', 'service', 'revision', 'container', 'serverless', 'deploy', 'traffic', 'image', 'knative', 'job']
    },
    "brave_search_agent_adk": {
        "agent_id": "brave_search_specialist",
        "keywords": ['search', 'find', 'lookup', 'web', 'internet', 'online', 'brave']
    },
    "filesystem_agent_adk": {
        "agent_id": "local_filesystem_specialist",
        "keywords": ['file', 'directory', 'folder', 'cat', 'ls', 'local file', 'read', 'write']
    },
    "analytics_agent_adk": {
        "agent_id": "google_analytics_specialist",
        "keywords": ['analytics', 'traffic', 'users', 'sessions', 'pageviews', 'ga4', 'report', 'visitor']
    },
    "puppeteer_agent_adk": {
        "agent_id": "browser_automation_specialist",
        "keywords": ['browser', 'screenshot', 'click', 'navigate', 'visit', 'scrape', 'form', 'webpage', 'puppeteer']
    },
    "sequential_thinking_agent_adk": {
        "agent_id": "sequential_thinking_specialist",
        "keywords": ['think', 'reason', 'plan', 'solve', 'analyze', 'complex', 'step by step']
    },
    "googlesearch_agent_adk": {
        "agent_id": "google_search_specialist",
        "keywords": ['search', 'google', 'find', 'lookup', 'web', 'internet', 'scraping']
    },
    "code_execution_agent_adk": {
        "agent_id": "python_code_execution_specialist",
        "keywords": ['code', 'execute', 'calculate', 'python', 'script', 'math', 'function', 'snippet']
    }
}

def backfill_manifests():
    base_dir = Path(__file__).parent.parent / "sub_agents"
    
    for agent_dir, data in KEYWORD_MAPPING.items():
        manifest_path = base_dir / agent_dir / "manifest.json"
        
        if manifest_path.exists():
            try:
                with open(manifest_path, 'r') as f:
                    manifest = json.load(f)
                
                # Check if we need to update
                needs_update = False
                if "keywords" not in manifest:
                    manifest["keywords"] = data["keywords"]
                    needs_update = True
                
                # Ensure agent_id matches known IDs (optional fix)
                # manifest["agent_id"] = data["agent_id"]
                
                if needs_update:
                    with open(manifest_path, 'w') as f:
                        json.dump(manifest, f, indent=4)
                    print(f"Updated {agent_dir}")
                else:
                    print(f"Skipped {agent_dir} (already valid)")
                    
            except Exception as e:
                print(f"Error processing {agent_dir}: {e}")
        else:
            print(f"Warning: Manifest not found for {agent_dir}")

if __name__ == "__main__":
    backfill_manifests()
