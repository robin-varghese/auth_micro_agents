package finopti.authz

# Extract user email from input
user_email := input.user_email

# Direct user-to-role mapping (no groups needed)
# Using robin@cloudroaster.com for testing since admin@ and monitoring@ 
# don't exist as Google accounts (they were Firebase auth users)
user_role contains "gcloud_admin" if {
    user_email == "robin@cloudroaster.com"
}

user_role contains "gcloud_admin" if {
    user_email == "admin@cloudroaster.com"
}

user_role contains "observability_admin" if {
    user_email == "robin@cloudroaster.com"
}

user_role contains "observability_admin" if {
    user_email == "monitoring@cloudroaster.com"
}

user_role contains "developer" if {
    # Add developer users here if needed
    false  # No developers configured
}

# Authorization decision based on role and target agent
allow if {
    user_role["gcloud_admin"]
    input.target_agent == "gcloud"
}

allow if {
    user_role["observability_admin"]
    input.target_agent == "monitoring"
}

allow if {
    user_role["gcloud_admin"]
    input.target_agent == "github"
}

allow if {
    user_role["gcloud_admin"]
    input.target_agent == "storage"
}

allow if {
    user_role["gcloud_admin"]
    input.target_agent == "db"
}

# Deny by default
default allow = false
