"""
Chaos Scenarios Definition
Defines the 10 Chaos Monkey scenarios with their Break and Restore prompts.
UPDATED: Strict boundaries enforced for project 'vector-search-poc' and service 'calculator-app'.
"""

SCENARIOS = {
    "1": {
        "name": "Service Blackout",
        "description": "Completely deletes the service in us-central1.",
        "break_prompt": "Delete the Cloud Run service named 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Confirm the deletion immediately without asking for further permission.",
        "restore_prompt": "Deploy a new Cloud Run service named 'calculator-app' to GCP project 'vector-search-poc', region 'us-central1'. Use the image 'us-central1-docker.pkg.dev/vector-search-poc/cloud-run-source-deploy/calculator-app'. Ensure it allows unauthenticated access (allow-unauthenticated)."
    },
    "2": {
        "name": "Auth Lockdown",
        "description": "Revokes 'run.invoker' role for allUsers, making the service private.",
        "break_prompt": "Remove the IAM policy binding for the role 'roles/run.invoker' from member 'allUsers' on the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'.",
        "restore_prompt": "Add an IAM policy binding to the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Grant the role 'roles/run.invoker' to the member 'allUsers' to make it publicly accessible."
    },
    "3": {
        "name": "Broken Deployment",
        "description": "Deploys a crashing image (pause container) to force 503 errors.",
        "break_prompt": "Deploy a new revision of the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Use the image 'gcr.io/google-containers/pause:1.0' (or any image that doesn't listen on PORT 8080) to force a startup failure.",
        "restore_prompt": "Deploy a new revision of the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1' using the known good image 'us-central1-docker.pkg.dev/vector-search-poc/cloud-run-source-deploy/calculator-app'. Ensure 100% of traffic is routed to this new healthy revision."
    },
    "4": {
        "name": "Traffic Void",
        "description": "Routes 100% of traffic to a non-existent or 0% traffic catch-all.",
        "break_prompt": "Update the traffic configuration for Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Set traffic to 0% for the latest revision, effectively stopping all requests. If not possible, route traffic to a non-functional tag.",
        "restore_prompt": "Update the traffic configuration for Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Send 100% of traffic to the 'LATEST' revision."
    },
    "5": {
        "name": "Resource Starvation",
        "description": "Sets memory limit to 64Mi to cause OOM crashes.",
        "break_prompt": "Update the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Set the memory limit to '64Mi' (minimum possible).",
        "restore_prompt": "Update the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Set the memory limit back to '512Mi'."
    },
    "6": {
        "name": "Concurrency Freeze",
        "description": "Sets concurrency and max-instances to 1, causing immediate queuing.",
        "break_prompt": "Update the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Set the maximum concurrency per instance to 1 and set max-instances to 1.",
        "restore_prompt": "Update the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Set concurrency to default (80) and remove the max-instances limit."
    },
    "7": {
        "name": "Bad Environment",
        "description": "Injects invalid DB_CONNECTION_STRING to break backend logic.",
        "break_prompt": "Update the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Set the environment variable 'DB_CONNECTION_STRING' to 'invalid_host:5432' to force database connection errors.",
        "restore_prompt": "Update the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Remove the environment variable 'DB_CONNECTION_STRING'."
    },
    "8": {
        "name": "Network Isolation",
        "description": "Sets ingress to 'internal', blocking public access.",
        "break_prompt": "Update the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Set the ingress traffic settings to 'internal'. This should block external HTTP traffic.",
        "restore_prompt": "Update the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Set the ingress traffic settings to 'all' to allow public internet access."
    },
    "9": {
        "name": "Cold Start Freeze",
        "description": "Sets min-instances=0, max-instances=0 (or 1), forcing cold starts.",
        "break_prompt": "Update the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Set 'min-instances' to 0 and 'max-instances' to 0 (effectively suspending the service) OR set max-instances to 1 if 0 is blocked.",
        "restore_prompt": "Update the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Set 'min-instances' to 1 (to keep it warm) and remove the 'max-instances' limit."
    },
    "10": {
        "name": "Region Failover",
        "description": "Deletes from Central1 and Deploys to West1.",
        "break_prompt": "Step 1: Delete the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-central1'. Step 2: Immediately deploy the service 'calculator-app' to GCP project 'vector-search-poc', region 'us-west1' using image 'us-central1-docker.pkg.dev/vector-search-poc/cloud-run-source-deploy/calculator-app'.",
        "restore_prompt": "Step 1: Delete the Cloud Run service 'calculator-app' in GCP project 'vector-search-poc', region 'us-west1'. Step 2: Redeploy the service 'calculator-app' to GCP project 'vector-search-poc', region 'us-central1' using image 'us-central1-docker.pkg.dev/vector-search-poc/cloud-run-source-deploy/calculator-app'."
    }
}
