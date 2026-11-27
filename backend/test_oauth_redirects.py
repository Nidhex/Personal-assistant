import os
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.main import app, current_worker_env
from backend.database import get_db, init_db
from backend.security import generate_session_id, get_session_expiry
from backend.google_service import (
    get_frontend_url,
    is_production,
    is_cookie_secure,
    is_dev_test_mode,
    get_google_auth_url
)

@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()
    conn = get_db()
    conn.execute("DELETE FROM sessions")
    conn.execute("DELETE FROM oauth_states")
    conn.execute("DELETE FROM users WHERE id LIKE 'usr_test_%'")
    conn.commit()
    conn.close()

class MockWorkerEnv:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

def test_production_login_redirect_never_localhost():
    """Verify that in production, frontend redirect is guaranteed to be deskagent.hacckthon.workers.dev and NEVER localhost."""
    env = MockWorkerEnv(
        ENVIRONMENT="production",
        FRONTEND_URL="https://deskagent.hacckthon.workers.dev",
        GOOGLE_REDIRECT_URI="https://deskagent.hacckthon.workers.dev/api/auth/google/callback"
    )
    token = current_worker_env.set(env)
    try:
        assert is_production() is True
        frontend_url = get_frontend_url()
        assert frontend_url == "https://deskagent.hacckthon.workers.dev"
        assert "localhost" not in frontend_url
        assert "127.0.0.1" not in frontend_url

        # Even if accidentally configured with localhost in prod, it must override
        env_bad = MockWorkerEnv(ENVIRONMENT="production", FRONTEND_URL="http://localhost:5173")
        current_worker_env.set(env_bad)
        frontend_url_override = get_frontend_url()
        assert frontend_url_override == "https://deskagent.hacckthon.workers.dev"
        assert "localhost" not in frontend_url_override

        # Verify Google auth URL redirect_uri
        auth_url = get_google_auth_url("state_123")
        assert "redirect_uri=https%3A%2F%2Fdeskagent.hacckthon.workers.dev%2Fapi%2Fauth%2Fgoogle%2Fcallback" in auth_url
        assert "localhost" not in auth_url
    finally:
        current_worker_env.reset(token)

def test_local_development_login_redirect():
    """Verify that in local development, frontend redirect preserves local development configuration."""
    with patch.dict(os.environ, {"ENVIRONMENT": "development", "FRONTEND_URL": "http://localhost:5173"}):
        current_worker_env.set(None)
        assert is_production() is False
        frontend_url = get_frontend_url()
        assert frontend_url == "http://localhost:5173"

def test_mobile_origin_login_redirect():
    """Verify that requests from mobile devices resolve properly in both production and dev."""
    # Production mobile request
    prod_scope = {
        "type": "http",
        "headers": [(b"host", b"deskagent.hacckthon.workers.dev"), (b"x-forwarded-proto", b"https")],
        "env": MockWorkerEnv(ENVIRONMENT="production", FRONTEND_URL="https://deskagent.hacckthon.workers.dev")
    }
    prod_req = Request(prod_scope)
    assert get_frontend_url(prod_req) == "https://deskagent.hacckthon.workers.dev"
    assert "localhost" not in get_frontend_url(prod_req)

    # Local dev mobile LAN request (e.g. testing from mobile device on Wi-Fi)
    with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
        dev_scope = {
            "type": "http",
            "headers": [(b"host", b"192.168.1.105:8001"), (b"x-forwarded-proto", b"http")],
            "env": None
        }
        dev_req = Request(dev_scope)
        lan_url = get_frontend_url(dev_req)
        assert lan_url == "http://192.168.1.105:5173"
        assert "localhost" not in lan_url

def test_oauth_callback_invalid_state():
    """Verify that invalid OAuth state redirects to frontend with error and never localhost in production."""
    env = MockWorkerEnv(
        ENVIRONMENT="production",
        FRONTEND_URL="https://deskagent.hacckthon.workers.dev"
    )
    token = current_worker_env.set(env)
    try:
        client = TestClient(app, base_url="https://deskagent.hacckthon.workers.dev")
        resp = client.get("/api/auth/google/callback?state=nonexistent_state&code=test_code", follow_redirects=False)
        assert resp.status_code in [302, 307]
        location = resp.headers["location"]
        assert location.startswith("https://deskagent.hacckthon.workers.dev/?auth_error=invalid_or_expired_state")
        assert "localhost" not in location
    finally:
        current_worker_env.reset(token)

@pytest.mark.asyncio
async def test_oauth_callback_success_and_session_persistence():
    """Verify full successful OAuth callback sets secure cookie, redirects to production frontend, and persists session."""
    env = MockWorkerEnv(
        ENVIRONMENT="production",
        FRONTEND_URL="https://deskagent.hacckthon.workers.dev",
        GOOGLE_CLIENT_ID="mock_cid",
        GOOGLE_CLIENT_SECRET="mock_csecret",
        GOOGLE_REDIRECT_URI="https://deskagent.hacckthon.workers.dev/api/auth/google/callback",
        COOKIE_SECURE="true"
    )
    token = current_worker_env.set(env)
    try:
        # 1. Insert valid state
        conn = get_db()
        test_state = "valid_test_state_12345"
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        conn.execute("INSERT INTO oauth_states (state, action, expires_at) VALUES (?, 'login', ?)", (test_state, expires_at))
        conn.commit()
        conn.close()

        # 2. Mock Google token exchange & profile
        mock_tokens = {
            "access_token": "ya29.mock_access_token",
            "refresh_token": "1//mock_refresh_token",
            "expires_in": 3600,
            "scope": "openid email profile https://www.googleapis.com/auth/gmail.readonly"
        }
        mock_profile = {
            "id": "test_google_user_999",
            "email": "mobile_user@example.com",
            "name": "Mobile Tester",
            "picture": "https://example.com/avatar.jpg"
        }

        with patch("backend.main.exchange_code_for_tokens", new_callable=AsyncMock) as mock_exch, \
             patch("backend.main.get_google_user_profile", new_callable=AsyncMock) as mock_prof:
            mock_exch.return_value = mock_tokens
            mock_prof.return_value = mock_profile

            client = TestClient(app, base_url="https://deskagent.hacckthon.workers.dev")
            resp = client.get(
                f"/api/auth/google/callback?state={test_state}&code=test_code_valid",
                headers={"Host": "deskagent.hacckthon.workers.dev"},
                follow_redirects=False
            )

            # Assert redirect to production frontend
            assert resp.status_code in [302, 307]
            location = resp.headers["location"]
            assert location.startswith("https://deskagent.hacckthon.workers.dev/?auth_success=1")
            assert "localhost" not in location
            assert "sid=" not in location
            assert "session_id=" not in location

            # Assert cookie attributes
            set_cookie = resp.headers.get("set-cookie", "")
            assert "session_id=" in set_cookie
            assert "HttpOnly" in set_cookie
            assert "Secure" in set_cookie
            assert "samesite=lax" in set_cookie.lower()

            # Extract session_id
            session_id = None
            for cookie in client.cookies.jar:
                if cookie.name == "session_id":
                    session_id = cookie.value
                    break
            assert session_id is not None

            # Verify session persistence via /api/auth/me with Cookie
            me_resp = client.get("/api/auth/me")
            assert me_resp.status_code == 200
            me_data = me_resp.json()
            assert me_data["authenticated"] is True
            assert me_data["user"]["email"] == "mobile_user@example.com"
            assert me_data["user"]["name"] == "Mobile Tester"

            # Verify session persistence via Authorization Bearer token header
            client_no_cookie = TestClient(app, base_url="https://deskagent.hacckthon.workers.dev")
            bearer_resp = client_no_cookie.get(
                "/api/auth/me",
                headers={"Authorization": f"Bearer {session_id}"}
            )
            assert bearer_resp.status_code == 200
            bearer_data = bearer_resp.json()
            assert bearer_data["authenticated"] is True
            assert bearer_data["user"]["email"] == "mobile_user@example.com"

    finally:
        current_worker_env.reset(token)

def test_dev_test_mode_strictly_forbidden_in_production():
    """Verify that /api/auth/dev-login is strictly blocked (HTTP 403) in production environment."""
    env = MockWorkerEnv(ENVIRONMENT="production", DEV_TEST_MODE="true")
    token = current_worker_env.set(env)
    try:
        client = TestClient(app, base_url="https://deskagent.hacckthon.workers.dev")
        resp = client.post("/api/auth/dev-login", json={"email": "hacker@test.local"})
        assert resp.status_code == 403
        assert "disabled in production" in resp.json()["detail"]
    finally:
        current_worker_env.reset(token)
