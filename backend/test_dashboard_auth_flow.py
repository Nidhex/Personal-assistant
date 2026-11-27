import pytest
import os
import unittest.mock as mock
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import get_db, init_db
from backend.security import generate_session_id, get_session_expiry

@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()
    conn = get_db()
    # Create test user and session
    user_id = "usr_test_dashboard_user"
    conn.execute("""
        INSERT OR REPLACE INTO users (id, email, name, picture, created_at)
        VALUES (?, 'dashboard_user@example.com', 'Dashboard User', 'https://example.com/pic.png', '2026-01-01T00:00:00Z')
    """, (user_id,))
    
    session_id = "test_dash_session_token_12345"
    expires_at = get_session_expiry(days=7)
    conn.execute("""
        INSERT OR REPLACE INTO sessions (session_id, user_id, expires_at, created_at)
        VALUES (?, ?, ?, '2026-01-01T00:00:00Z')
    """, (session_id, user_id, expires_at))

    conn.execute("""
        INSERT OR REPLACE INTO user_tokens (user_id, access_token_encrypted, refresh_token_encrypted, token_expiry, scopes, gmail_connected, updated_at)
        VALUES (?, 'enc_acc', 'enc_ref', '2030-01-01T00:00:00Z', 'openid email', 1, '2026-01-01T00:00:00Z')
    """, (user_id,))

    conn.commit()
    conn.close()

    return {"session_id": session_id, "user_id": user_id}

def test_auth_me_with_cookie_and_bearer(setup_test_db):
    client = TestClient(app)
    sid = setup_test_db["session_id"]

    # Test via Cookie
    res_cookie = client.get("/api/auth/me", cookies={"session_id": sid})
    assert res_cookie.status_code == 200
    data = res_cookie.json()
    assert data["authenticated"] is True
    assert data["user"]["email"] == "dashboard_user@example.com"
    assert data["gmail_connected"] is True

    # Test via Authorization Bearer header
    res_bearer = client.get("/api/auth/me", headers={"Authorization": f"Bearer {sid}"})
    assert res_bearer.status_code == 200
    data_b = res_bearer.json()
    assert data_b["authenticated"] is True
    assert data_b["user"]["id"] == setup_test_db["user_id"]

def test_user_data_endpoint_success(setup_test_db):
    client = TestClient(app)
    sid = setup_test_db["session_id"]

    # Call /api/user/data
    res = client.get("/api/user/data", headers={"Authorization": f"Bearer {sid}"})
    assert res.status_code == 200
    data = res.json()
    assert "tasks" in data
    assert "workspaces" in data
    assert "approvals" in data
    assert "activity" in data
    assert "calendar_events" in data
    assert "agent_settings" in data
    assert isinstance(data["agent_settings"], dict)
    assert data["agent_settings"].get("user_id") == setup_test_db["user_id"]

def test_gmail_messages_graceful_error_handling(setup_test_db):
    client = TestClient(app)
    sid = setup_test_db["session_id"]

    with mock.patch("backend.main.fetch_gmail_messages", side_effect=Exception("Worker subrequest limit exceeded")):
        res = client.get("/api/gmail/messages", headers={"Authorization": f"Bearer {sid}"})
        # Must return 200 with connected=False and error message instead of 500 crash
        assert res.status_code == 200
        data = res.json()
        assert data["connected"] is False
        assert "Worker subrequest limit exceeded" in data["error"]

def test_agent_settings_get_and_save(setup_test_db):
    client = TestClient(app)
    sid = setup_test_db["session_id"]

    # GET /api/agent/settings
    res = client.get("/api/agent/settings", headers={"Authorization": f"Bearer {sid}"})
    assert res.status_code == 200
    assert "settings" in res.json()

    # POST /api/agent/settings
    update_res = client.post(
        "/api/agent/settings",
        json={"preferred_time": "09:30", "timezone": "America/New_York"},
        headers={"Authorization": f"Bearer {sid}"}
    )
    assert update_res.status_code == 200
    assert update_res.json()["success"] is True
    assert update_res.json()["settings"]["preferred_time"] == "09:30"

def test_multi_user_isolation(setup_test_db):
    client = TestClient(app)
    conn = get_db()

    # User B setup
    user_b_id = "usr_test_user_b"
    session_b_id = "test_dash_session_token_user_b"
    conn.execute("INSERT OR REPLACE INTO users (id, email, name, picture, created_at) VALUES (?, 'user_b@example.com', 'User B', '', '2026-01-01T00:00:00Z')", (user_b_id,))
    conn.execute("INSERT OR REPLACE INTO sessions (session_id, user_id, expires_at, created_at) VALUES (?, ?, ?, '2026-01-01T00:00:00Z')", (session_b_id, user_b_id, get_session_expiry(days=7)))
    conn.execute("INSERT INTO user_tasks (id, user_id, title, source, created_at) VALUES ('tsk_b_1', ?, 'Task For User B Only', 'test', '2026-01-01T00:00:00Z')", (user_b_id,))
    conn.commit()
    conn.close()

    # User A requests /api/user/data
    res_a = client.get("/api/user/data", headers={"Authorization": f"Bearer {setup_test_db['session_id']}"})
    assert res_a.status_code == 200
    task_titles_a = [t["title"] for t in res_a.json()["tasks"]]
    assert "Task For User B Only" not in task_titles_a

    # User B requests /api/user/data
    res_b = client.get("/api/user/data", headers={"Authorization": f"Bearer {session_b_id}"})
    assert res_b.status_code == 200
    task_titles_b = [t["title"] for t in res_b.json()["tasks"]]
    assert "Task For User B Only" in task_titles_b

def test_logout_invalidates_session(setup_test_db):
    client = TestClient(app)
    sid = setup_test_db["session_id"]

    # Verify initially authenticated
    res_before = client.get("/api/auth/me", headers={"Authorization": f"Bearer {sid}"})
    assert res_before.status_code == 200
    assert res_before.json()["authenticated"] is True

    # Logout
    logout_res = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {sid}"})
    assert logout_res.status_code == 200
    assert logout_res.json()["success"] is True

    # Verify session is destroyed in DB and /api/auth/me returns unauthenticated
    res_after = client.get("/api/auth/me", headers={"Authorization": f"Bearer {sid}"})
    assert res_after.status_code == 200
    assert res_after.json()["authenticated"] is False
    assert res_after.json()["user"] is None

def test_expired_session_rejected(setup_test_db):
    client = TestClient(app)
    conn = get_db()
    expired_sid = "test_expired_session_token_999"
    conn.execute("INSERT OR REPLACE INTO sessions (session_id, user_id, expires_at, created_at) VALUES (?, ?, '2020-01-01T00:00:00Z', '2020-01-01T00:00:00Z')", (expired_sid, setup_test_db["user_id"]))
    conn.commit()
    conn.close()

    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_sid}"})
    assert res.status_code == 200
    assert res.json()["authenticated"] is False
    assert res.json()["user"] is None
