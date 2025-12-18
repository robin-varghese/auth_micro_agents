package finopti

# Default deny
default allow = false

# User role mapping
user_roles := {
    "admin@cloudroaster.com": "gcloud_admin",
    "monitoring@cloudroaster.com": "observability_admin",
    "robin@cloudroaster.com": "developer"
}

# Role to agent access mapping
role_permissions := {
    "gcloud_admin": ["gcloud"],
    "observability_admin": ["monitoring"],
    "developer": []
}

# Authorization logic
authz := {
    "allow": allow,
    "reason": reason
}

# Check if user has role and role has permission for target agent
allow {
    user_email := input.user_email
    target_agent := input.target_agent
    
    role := user_roles[user_email]
    allowed_agents := role_permissions[role]
    
    target_agent in allowed_agents
}

# Reason for denial - user not found
reason := "User not found in system" {
    not user_roles[input.user_email]
}

# Reason for denial - insufficient permissions
reason := sprintf("User role '%s' does not have access to '%s' agent", [role, input.target_agent]) {
    user_email := input.user_email
    target_agent := input.target_agent
    role := user_roles[user_email]
    allowed_agents := role_permissions[role]
    not target_agent in allowed_agents
}

# Reason for success
reason := sprintf("Access granted: User '%s' with role '%s' can access '%s' agent", [input.user_email, role, input.target_agent]) {
    allow
    user_email := input.user_email
    target_agent := input.target_agent
    role := user_roles[user_email]
}
