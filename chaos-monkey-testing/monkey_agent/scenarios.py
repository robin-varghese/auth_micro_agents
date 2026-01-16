"""
Chaos Scenarios Definition
Defines the 10 Chaos Monkey scenarios with their Break and Restore prompts.
UPDATED: Strict boundaries enforced for project 'vector-search-poc' and service 'calculator-app'.
"""

SCENARIOS = {
    "1": {
        "name": "Service Blackout",
        "description": "Completely deletes the service in us-central1.",
        "technical_explanation": "This scenario simulates a catastrophic accidental deletion or region-wide failure where the service resource ceases to exist.",
        "steps": [
            "Authenticate as Cloud Run Admin.",
            "Identify the target service 'calculator-app' in 'us-central1'.",
            "Execute 'gcloud run services delete' command.",
            "Verify service is no longer listed."
        ],
        "break_prompt": "Delete the Cloud Run service named 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Confirm the deletion immediately without asking for further permission.",
        "restore_prompt": "Deploy a new Cloud Run service named 'calculator-app' to GCP project 'vector-search-poc', region 'us-central1'. Use the image 'us-central1-docker.pkg.dev/vector-search-poc/cloud-run-source-deploy/calculator-app'. Ensure it allows unauthenticated access (allow-unauthenticated)."
    },
    "2": {
        "name": "Auth Lockdown",
        "description": "Revokes 'run.invoker' role for allUsers, making the service private.",
        "technical_explanation": "This scenario modifies the IAM policy binding of the service, removing public access permissions. This simulates a misconfiguration where a public service accidentally becomes private.",
        "steps": [
            "Fetch current IAM policy for the service.",
            "Identify binding for 'roles/run.invoker' assigned to 'allUsers'.",
            "Remove this specific binding.",
            "Apply the updated IAM policy."
        ],
        "break_prompt": "Remove the IAM policy binding for the role 'roles/run.invoker' from member 'allUsers' on the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'.",
        "restore_prompt": "Add an IAM policy binding to the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Grant the role 'roles/run.invoker' to the member 'allUsers' to make it publicly accessible."
    },
    "3": {
        "name": "Broken Deployment",
        "description": "Deploys a crashing image (pause container) to force 503 errors.",
        "technical_explanation": "This scenario attempts to deploy a broken image (pause container) that fails to start. Cloud Run's safety mechanisms should detect this failure (health check) and block the traffic shift, preserving the service's availability. This validates that your service is protected against bad deployments.",
        "steps": [
            "Attempt to deploy revision using broken image 'gcr.io/google-containers/pause:1.0'.",
            "Cloud Run detects startup failure (health check).",
            "Traffic migration is BLOCKED by Cloud Run.",
            "Service remains healthy on the previous revision (Resilience Success)."
        ],
        "break_prompt": "Deploy a new revision of the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Use the image 'gcr.io/google-containers/pause:1.0' (or any image that doesn't listen on PORT 8080) to force a startup failure.",
        "restore_prompt": "Deploy a new revision of the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1' using the known good image 'us-central1-docker.pkg.dev/vector-search-poc/cloud-run-source-deploy/calculator-app'. Ensure 100% of traffic is routed to this new healthy revision."
    },
    "4": {
        "name": "Traffic Void",
        "description": "Routes 100% of traffic to a non-existent or 0% traffic catch-all.",
        "technical_explanation": "This scenario manipulates the traffic splitting configuration. It routes 100% of traffic to a specific revision or tag that is not serving, or effectively removes the 'LATEST' route, causing 404s or 503s.",
        "steps": [
            "Identify current traffic split (usually 100% to LATEST).",
            "Update traffic rules to send 0% to LATEST.",
            "Alternatively, route traffic to a non-functional tag.",
            "Apply traffic split update."
        ],
        "break_prompt": "Update the traffic configuration for Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Set traffic to 0% for the latest revision, effectively stopping all requests. If not possible, route traffic to a non-functional tag.",
        "restore_prompt": "Update the traffic configuration for Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Send 100% of traffic to the 'LATEST' revision."
    },
    "5": {
        "name": "Resource Starvation",
        "description": "Sets memory limit to 64Mi to cause OOM crashes.",
        "technical_explanation": "This scenario updates the service configuration to forcefully reduce the allocated memory per instance to the minimum allowed (64Mi). It then sends a massive burst of requests (500+) to cause the application to crash with OutOfMemory (OOM) errors under load.",
        "steps": [
            "Fetch current service configuration.",
            "Update 'memory' limit to '64Mi'.",
            "Deploy this as a new revision.",
            "Send 500+ concurrent requests to trigger OOM."
        ],
        "break_prompt": "Update the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Set the memory limit to '64Mi' (minimum possible). After updating, make 500 HTTP requests to the service URL to trigger the OOM crash.",
        "restore_prompt": "Update the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Set the memory limit back to '512Mi'."
    },
    "6": {
        "name": "Concurrency Freeze",
        "description": "Sets concurrency and max-instances to 1, causing immediate queuing.",
        "technical_explanation": "This scenario artificially constrains the scaling ability of the service. By setting max-instances to 1 and concurrency to 1, the service can only handle one request at a time, causing massive latency and 429 Too Many Requests errors.",
        "steps": [
            "Fetch current scaling configuration.",
            "Set 'concurrency' to 1.",
            "Set 'max-instances' to 1.",
            "Update service configuration."
        ],
        "break_prompt": "Update the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Set the maximum concurrency per instance to 1 and set max-instances to 1.",
        "restore_prompt": "Update the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Set concurrency to default (80) and remove the max-instances limit."
    },
    "7": {
        "name": "Bad Environment",
        "description": "Injects invalid DB_CONNECTION_STRING to break backend logic.",
        "technical_explanation": "This scenario injects a poisonous environment variable. The application logic (if it uses this variable) will try to connect to an invalid endpoint, causing internal server errors (500) without crashing the container itself.",
        "steps": [
            "Prepare update command.",
            "Set environment variable 'DB_CONNECTION_STRING' to 'invalid_host:5432'.",
            "Deploy new revision with this config.",
            "App logic fails when using this variable."
        ],
        "break_prompt": "Update the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Set the environment variable 'DB_CONNECTION_STRING' to 'invalid_host:5432' to force database connection errors.",
        "restore_prompt": "Update the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Remove the environment variable 'DB_CONNECTION_STRING'."
    },
    "8": {
        "name": "Network Isolation",
        "description": "Sets ingress to 'internal', blocking public access.",
        "technical_explanation": "This scenario restricts the network ingress settings. Setting ingress to 'internal' means the service is only accessible from within the VPC or other Google Cloud resources, blocking all public internet traffic (403 Forbidden).",
        "steps": [
            "Fetch current ingress settings.",
            "Set ingress to 'internal'.",
            "Apply update.",
            "Public access is immediately revoked."
        ],
        "break_prompt": "Update the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Set the ingress traffic settings to 'internal'. This should block external HTTP traffic.",
        "restore_prompt": "Update the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Set the ingress traffic settings to 'all' to allow public internet access."
    },
    "9": {
        "name": "Cold Start Freeze",
        "description": "Sets min-instances=0, max-instances=0 (or 1), forcing cold starts.",
        "technical_explanation": "This scenario prevents the service from scaling up. Setting max-instances to 0 effectively suspends the service. Even with max-instances=1, any concurrent load will fail.",
        "steps": [
            "Fetch autoscaling config.",
            "Set 'min-instances' to 0.",
            "Set 'max-instances' to 0 (or 1).",
            "Update service."
        ],
        "break_prompt": "Update the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Set 'min-instances' to 0 and 'max-instances' to 0 (effectively suspending the service) OR set max-instances to 1 if 0 is blocked.",
        "restore_prompt": "Update the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Set 'min-instances' to 1 (to keep it warm) and remove the 'max-instances' limit."
    },
    "10": {
        "name": "Region Failover",
        "description": "Deletes from Central1 and Deploys to West1.",
        "technical_explanation": "This scenario simulates a region evacuation. The service is deleted from its primary region (us-central1) and redeployed to a different region (us-west1), testing multi-region resilience or failover logic.",
        "steps": [
            "Delete service in 'us-central1'.",
            "Deploy same image/config to 'us-west1'.",
            "Service is now running in a new location.",
            "DNS/Traffic routing would need to update (simulated)."
        ],
        "break_prompt": "Step 1: Delete the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Step 2: Immediately deploy the service 'calculator-app' to GCP project 'vector-search-poc', region 'us-west1' using image 'us-central1-docker.pkg.dev/vector-search-poc/cloud-run-source-deploy/calculator-app'.",
        "restore_prompt": "Step 1: Delete the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-west1'. Step 2: Redeploy the service 'calculator-app' to GCP project 'vector-search-poc', region 'us-central1' using image 'us-central1-docker.pkg.dev/vector-search-poc/cloud-run-source-deploy/calculator-app'."
    }
}
