"""
FinOptiAgents - OAuth Helper Module

Handles Google OAuth 2.0 authentication flow with Secret Manager integration.
Supports both OAuth and simulated auth for development.
"""

import os
import streamlit as st
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from typing import Optional, Dict

# Try to load OAuth credentials from Secret Manager
try:
    from oauth_config import load_oauth_config
    _oauth_config = load_oauth_config()
    GOOGLE_CLIENT_ID = _oauth_config.get('client_id', '')
    GOOGLE_CLIENT_SECRET = _oauth_config.get('client_secret', '')
    REDIRECT_URI = _oauth_config.get('redirect_uri', 'http://localhost:8501/_oauth_callback')
    CREDENTIALS_SOURCE = "Secret Manager"
except Exception as e:
    # Fallback to environment variables if Secret Manager fails
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    REDIRECT_URI = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8501/_oauth_callback")
    CREDENTIALS_SOURCE = f"Environment Variables (Secret Manager failed: {str(e)[:30]}...)"

# Feature flag: OAuth enabled if credentials configured
OAUTH_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def get_oauth_login_url() -> str:
    """Generate Google OAuth login URL"""
    if not OAUTH_ENABLED:
        return ""
    
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent"
    }
    
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    return f"https://accounts.google.com/o/oauth2/v2/auth?{query_string}"


def exchange_code_for_token(auth_code: str) -> Optional[Dict]:
    """Exchange authorization code for tokens"""
    if not OAUTH_ENABLED:
        return None
    
    try:
        import requests
        
        token_endpoint = "https://oauth2.googleapis.com/token"
        token_data = {
            'code': auth_code,
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'redirect_uri': REDIRECT_URI,
            'grant_type': 'authorization_code'
        }
        
        response = requests.post(token_endpoint, data=token_data, timeout=10)
        response.raise_for_status()
        
        return response.json()
    except Exception as e:
        st.error(f"Token exchange failed: {e}")
        return None


def verify_id_token(id_token_jwt: str) -> Optional[Dict]:
    """Verify and decode Google ID token"""
    if not OAUTH_ENABLED:
        return None
    
    try:
        user_info = id_token.verify_oauth2_token(
            id_token_jwt,
            google_requests.Request(),
            GOOGLE_CLIENT_ID
        )
        
        # Verify issuer
        if user_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('Wrong issuer')
        
        return user_info
    except Exception as e:
        st.error(f"Token verification failed: {e}")
        return None


def handle_oauth_callback() -> bool:
    """
    Handle OAuth callback and complete authentication.
    Returns True if authentication successful.
    """
    if not OAUTH_ENABLED:
        return False
    
    # Check for authorization code in URL params
    query_params = st.query_params
    
    if 'code' not in query_params:
        return False
    
    auth_code = query_params['code']
    
    # Exchange code for tokens
    tokens = exchange_code_for_token(auth_code)
    if not tokens:
        return False
    
    # Verify ID token
    id_token_jwt = tokens.get('id_token')
    if not id_token_jwt:
        st.error("No ID token in response")
        return False
    
    user_info = verify_id_token(id_token_jwt)
    if not user_info:
        return False
    
    # Store in session
    st.session_state.authenticated = True
    st.session_state.user_email = user_info.get('email')
    st.session_state.user_name = user_info.get('name', user_info.get('email'))
    st.session_state.id_token = id_token_jwt
    st.session_state.access_token = tokens.get('access_token')
    st.session_state.auth_method = 'oauth'
    
    # Clear query params to prevent re-processing
    st.query_params.clear()
    
    return True


def logout():
    """Clear authentication session"""
    st.session_state.authenticated = False
    st.session_state.user_email = None
    st.session_state.user_name = None
    st.session_state.id_token = None
    st.session_state.access_token = None
    st.session_state.auth_method = None
    st.session_state.messages = []


def get_auth_headers() -> Dict[str, str]:
    """Get authentication headers for API requests"""
    headers = {
        "Content-Type": "application/json",
        "X-User-Email": st.session_state.get('user_email', '')
    }
    
    # Add Bearer token if OAuth authenticated
    if st.session_state.get('auth_method') == 'oauth' and st.session_state.get('id_token'):
        headers["Authorization"] = f"Bearer {st.session_state.id_token}"
    
    return headers


def is_oauth_enabled() -> bool:
    """Check if OAuth is enabled"""
    return OAUTH_ENABLED


def get_oauth_status() -> str:
    """Get OAuth configuration status for debugging"""
    if OAUTH_ENABLED:
        return f"✅ OAuth Enabled ({CREDENTIALS_SOURCE})"
    else:
        return f"⚠️ OAuth Disabled - {CREDENTIALS_SOURCE}"
