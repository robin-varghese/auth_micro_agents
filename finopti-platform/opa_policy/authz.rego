package finopti.authz

# Extract user email from input
user_email := input.user_email

# --- ROLE ASSIGNMENTS ---

# Admin / Superuser (Full Access)
user_role contains "gcloud_admin" if {
    user_email == "robin@cloudroaster.com"
}

user_role contains "gcloud_admin" if {
    user_email == "admin@cloudroaster.com"
}

# Monitoring User (Observability Access Only)
user_role contains "observability_admin" if {
    user_email == "monitoring@cloudroaster.com"
}

# Developer (Limited Access)
user_role contains "developer" if {
    # Add developer emails here
    false
}

# --- ALLOW RULES ---

# gcloud_admin allows access to EVERYTHING (All Services)
allow if {
    user_role["gcloud_admin"]
}

# observability_admin allows access to specific monitoring agents
allow if {
    user_role["observability_admin"]
    # Allow new verbose ID or old short ID
    allowed_monitoring_agents[input.target_agent]
}

allowed_monitoring_agents := {
    "monitoring",
    "cloud_monitoring_specialist",
    "analytics_specialist",
    "analytics"
}

# Deny by default
default allow = false
