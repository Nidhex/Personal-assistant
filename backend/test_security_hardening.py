"""
Comprehensive Security Hardening Regression Tests.
Covers:
- Phase 2: Kill Switch Server-Authoritative Enforcement & Bypass Prevention
- Phase 3: Session Security & URL Exposure Removal
- Phase 4: Mandatory Approvals for Calendar Mutations
- Phase 5: Ambiguous Calendar Mutation Prevention & Revalidation
- Phase 6: Strict CORS Origin Enforcement without Wildcards
"""
import os
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from backend.main import app, get_current_user
from backend.database import get_db, init_db
from backend.security import generate_session_id, get_session_expiry
from backend.agent import execute_policy_gate_and_tools
from backend.orchestrator import execute_daily_run

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture(autouse=True)
def setup_security_db():
    init_db()
    conn = get_db()
    cursor = conn.cursor()
    # Clean up test records
    cursor.execute("DELETE FROM user_activity WHERE user_id LIKE 'sec_%'")
    cursor.execute("DELETE FROM user_approvals WHERE user_id LIKE 'sec_%'")
    cursor.execute("DELETE FROM user_calendar_events WHERE user_id LIKE 'sec_%'")
    cursor.execute("DELETE FROM user_tasks WHERE user_id LIKE 'sec_%'")
    cursor.execute("DELETE FROM conversations WHERE user_id LIKE 'sec_%'")
    cursor.execute("DELETE FROM user_agent_settings WHERE user_id LIKE 'sec_%'")
    cursor.execute("DELETE FROM sessions WHERE user_id LIKE 'sec_%'")
    cursor.execute("DELETE FROM users WHERE id LIKE 'sec_%' OR email LIKE '%@sec.local'")
    conn.commit()
    conn.close()
    yield
    # Teardown
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_activity WHERE user_id LIKE 'sec_%'")
    cursor.execute("DELETE FROM user_approvals WHERE user_id LIKE 'sec_%'")
    cursor.execute("DELETE FROM user_calendar_events WHERE user_id LIKE 'sec_%'")
    cursor.execute("DELETE FROM user_tasks WHERE user_id LIKE 'sec_%'")
    cursor.execute("DELETE FROM conversations WHERE user_id LIKE 'sec_%'")
    cursor.execute("DELETE FROM user_agent_settings WHERE user_id LIKE 'sec_%'")
    cursor.execute("DELETE FROM sessions WHERE user_id LIKE 'sec_%'")
    cursor.execute("DELETE FROM users WHERE id LIKE 'sec_%' OR email LIKE '%@sec.local'")
    conn.commit()
    conn.close()


def _create_user(user_id: str, email: str, name: str = "Test User") -> str:
    conn = get_db()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "INSERT OR REPLACE INTO users (id, email, name, picture, created_at) VALUES (?, ?, ?, '', ?)",
        (user_id, email, name, now_iso)
    )
    sid = generate_session_id()
    cursor.execute(
        "INSERT INTO sessions (session_id, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (sid, user_id, get_session_expiry(7), now_iso)
    )
    cursor.execute(
        "INSERT INTO user_agent_settings (user_id, kill_switch_enabled, updated_at) VALUES (?, 0, ?)",
        (user_id, now_iso)
    )
    conn.commit()
    conn.close()
    return sid


# ==============================================================================
# PHASE 2 REGRESSION TESTS: KILL SWITCH AUTHORITATIVE ENFORCEMENT
# ==============================================================================

def test_kill_switch_enabled_in_db_browser_sends_false(client):
    """Kill switch enabled in DB (1), browser sends kill_switch_active: false. Must be blocked."""
    uid = "sec_test_ks_1"
    sid = _create_user(uid, "ks1@sec.local")
    
    # Enable kill switch in database
    conn = get_db()
    conn.execute("UPDATE user_agent_settings SET kill_switch_enabled = 1 WHERE user_id = ?", (uid,))
    # Create conversation
    cid = "conv_ks_1"
    conn.execute("INSERT INTO conversations (id, user_id, workspace_id, title, created_at, updated_at) VALUES (?, ?, 'main', 'Test', ?, ?)",
                 (cid, uid, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()

    # Browser attempts bypass by sending false
    res = client.post(
        f"/api/chat/conversations/{cid}/messages",
        json={"content": "Create a task called Deploy Production", "kill_switch_active": False},
        cookies={"session_id": sid}
    )
    assert res.status_code == 200
    data = res.json()
    assert "halted by the emergency kill switch" in data["assistant_message"]["content"].lower()

    # Verify task was NOT created in DB
    conn = get_db()
    t = conn.execute("SELECT id FROM user_tasks WHERE user_id = ?", (uid,)).fetchone()
    conn.close()
    assert t is None


def test_kill_switch_disabled_in_db_browser_sends_true(client):
    """Kill switch disabled in DB (0), browser sends kill_switch_active: true. Saved setting is authoritative."""
    uid = "sec_test_ks_2"
    sid = _create_user(uid, "ks2@sec.local")

    conn = get_db()
    cid = "conv_ks_2"
    conn.execute("INSERT INTO conversations (id, user_id, workspace_id, title, created_at, updated_at) VALUES (?, ?, 'main', 'Test', ?, ?)",
                 (cid, uid, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()

    # Browser sends true, but DB has 0
    res = client.post(
        f"/api/chat/conversations/{cid}/messages",
        json={"content": "Create a task called Write Unit Tests", "kill_switch_active": True},
        cookies={"session_id": sid}
    )
    assert res.status_code == 200
    data = res.json()
    # Action must NOT be blocked by kill switch because DB setting is authoritative (0)
    assert "emergency kill switch" not in data["assistant_message"]["content"].lower()


def test_kill_switch_activated_while_old_tab_open(client):
    """Old tab sends stale request with kill_switch_active: false after kill switch was activated in DB."""
    uid = "sec_test_ks_3"
    sid = _create_user(uid, "ks3@sec.local")

    conn = get_db()
    cid = "conv_ks_3"
    conn.execute("INSERT INTO conversations (id, user_id, workspace_id, title, created_at, updated_at) VALUES (?, ?, 'main', 'Test', ?, ?)",
                 (cid, uid, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()

    # User toggles kill switch ON in another tab or settings view
    res_toggle = client.post(
        "/api/agent/kill-switch",
        json={"enabled": True},
        cookies={"session_id": sid}
    )
    assert res_toggle.status_code == 200
    assert res_toggle.json()["kill_switch_enabled"] is True

    # Stale tab sends request with kill_switch_active: false
    res_msg = client.post(
        f"/api/chat/conversations/{cid}/messages",
        json={"content": "Create a task called Server Upgrade", "kill_switch_active": False},
        cookies={"session_id": sid}
    )
    assert res_msg.status_code == 200
    assert "emergency kill switch" in res_msg.json()["assistant_message"]["content"].lower()


def test_direct_api_request_attempts_execution(client):
    """Direct API request without kill_switch_active field halts execution when kill switch is active."""
    uid = "sec_test_ks_4"
    sid = _create_user(uid, "ks4@sec.local")

    conn = get_db()
    conn.execute("UPDATE user_agent_settings SET kill_switch_enabled = 1 WHERE user_id = ?", (uid,))
    cid = "conv_ks_4"
    conn.execute("INSERT INTO conversations (id, user_id, workspace_id, title, created_at, updated_at) VALUES (?, ?, 'main', 'Test', ?, ?)",
                 (cid, uid, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()

    # Direct request without any kill switch parameter
    res = client.post(
        f"/api/chat/conversations/{cid}/messages",
        json={"content": "Create a task called Direct API Test"},
        cookies={"session_id": sid}
    )
    assert res.status_code == 200
    assert "emergency kill switch" in res.json()["assistant_message"]["content"].lower()

    # Direct trigger of agent run
    res_run = client.post(
        "/api/agent/runs/trigger",
        cookies={"session_id": sid}
    )
    assert res_run.status_code == 200
    assert res_run.json()["status"] == "stopped_by_kill_switch"


@pytest.mark.asyncio
async def test_scheduled_execution_while_disabled():
    """Scheduled execution halts immediately and logs refusal when kill switch is enabled."""
    uid = "sec_test_ks_5"
    _create_user(uid, "ks5@sec.local")

    conn = get_db()
    conn.execute("UPDATE user_agent_settings SET kill_switch_enabled = 1 WHERE user_id = ?", (uid,))
    conn.commit()
    conn.close()

    result = await execute_daily_run(uid, trigger_type="scheduled")
    assert result["success"] is False
    assert result["status"] == "stopped_by_kill_switch"
    assert "emergency kill switch" in result["message"].lower()


def test_kill_switch_multi_user_isolation(client):
    """User A's kill switch does NOT affect User B's execution."""
    uid_a = "sec_test_ks_alice"
    sid_a = _create_user(uid_a, "alice.ks@sec.local")
    uid_b = "sec_test_ks_bob"
    sid_b = _create_user(uid_b, "bob.ks@sec.local")

    conn = get_db()
    # Engage kill switch ONLY for Alice
    conn.execute("UPDATE user_agent_settings SET kill_switch_enabled = 1 WHERE user_id = ?", (uid_a,))
    # Bob's kill switch is 0
    conn.execute("UPDATE user_agent_settings SET kill_switch_enabled = 0 WHERE user_id = ?", (uid_b,))

    cid_a = "conv_ks_alice"
    cid_b = "conv_ks_bob"
    now_iso = datetime.now(timezone.utc).isoformat()
    conn.execute("INSERT INTO conversations (id, user_id, workspace_id, title, created_at, updated_at) VALUES (?, ?, 'main', 'Alice', ?, ?)", (cid_a, uid_a, now_iso, now_iso))
    conn.execute("INSERT INTO conversations (id, user_id, workspace_id, title, created_at, updated_at) VALUES (?, ?, 'main', 'Bob', ?, ?)", (cid_b, uid_b, now_iso, now_iso))
    conn.commit()
    conn.close()

    # Alice is blocked
    res_a = client.post(
        f"/api/chat/conversations/{cid_a}/messages",
        json={"content": "Create a task called Alice Task"},
        cookies={"session_id": sid_a}
    )
    assert "emergency kill switch" in res_a.json()["assistant_message"]["content"].lower()

    # Bob executes normally
    res_b = client.post(
        f"/api/chat/conversations/{cid_b}/messages",
        json={"content": "Create a task called Bob Task"},
        cookies={"session_id": sid_b}
    )
    assert "emergency kill switch" not in res_b.json()["assistant_message"]["content"].lower()


# ==============================================================================
# PHASE 3 REGRESSION TESTS: REMOVE SESSION IDS FROM URLS & SECURE SESSIONS
# ==============================================================================

def test_oauth_callback_does_not_expose_session_id_in_url(client):
    """OAuth callback must redirect with auth_success=1 and NEVER include sid or session_id in URL."""
    state = "test_valid_oauth_state_secure"
    conn = get_db()
    conn.execute("INSERT INTO oauth_states (state, action, expires_at) VALUES (?, 'login', ?)",
                 (state, (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()))
    conn.commit()
    conn.close()

    mock_tokens = {
        "access_token": "ya29.test_token",
        "refresh_token": "1//test_refresh",
        "expires_in": 3600,
        "scope": "openid email profile"
    }
    mock_profile = {
        "id": "google_sub_12345",
        "email": "sec_test_oauth@example.com",
        "name": "Secure OAuth User",
        "picture": "https://example.com/pic.jpg"
    }

    with patch("backend.main.exchange_code_for_tokens", new=AsyncMock(return_value=mock_tokens)), \
         patch("backend.main.get_google_user_profile", new=AsyncMock(return_value=mock_profile)):
        resp = client.get(
            f"/api/auth/google/callback?state={state}&code=test_code_123",
            follow_redirects=False
        )

        assert resp.status_code in [302, 307]
        location = resp.headers.get("location", "")
        # Session ID must NOT be present in URL parameters
        assert "sid=" not in location
        assert "session_id=" not in location
        assert "auth_success=1" in location

        # Session established via secure cookie
        set_cookie = resp.headers.get("set-cookie", "")
        assert "session_id=" in set_cookie
        assert "HttpOnly" in set_cookie


def test_session_cannot_be_obtained_from_url_parameters(client):
    """Passing ?session_id=... or ?sid=... in query parameters without cookie or auth header returns 401."""
    uid = "sec_test_url_tamper"
    sid = _create_user(uid, "tamper@sec.local")

    # Attempt query string session authentication
    res1 = client.get(f"/api/auth/me?session_id={sid}")
    assert res1.status_code == 200
    assert res1.json()["authenticated"] is False

    res2 = client.get(f"/api/auth/me?sid={sid}")
    assert res2.status_code == 200
    assert res2.json()["authenticated"] is False

    res_data = client.get(f"/api/user/data?session_id={sid}")
    assert res_data.status_code == 401


def test_successful_login_and_refresh_preserves_authentication(client):
    """Cookie-based session successfully authenticates and persists across requests."""
    uid = "sec_test_cookie_flow"
    sid = _create_user(uid, "cookie_flow@sec.local")

    # Initial check with cookie
    res = client.get("/api/auth/me", cookies={"session_id": sid})
    assert res.status_code == 200
    data = res.json()
    assert data["authenticated"] is True
    assert data["user"]["email"] == "cookie_flow@sec.local"

    # Subsequent refresh preserves authentication
    res_refresh = client.get("/api/auth/me", cookies={"session_id": sid})
    assert res_refresh.status_code == 200
    assert res_refresh.json()["authenticated"] is True


def test_logout_invalidates_session(client):
    """Logout deletes session record and clears cookie."""
    uid = "sec_test_logout"
    sid = _create_user(uid, "logout@sec.local")

    res_logout = client.post("/api/auth/logout", cookies={"session_id": sid})
    assert res_logout.status_code == 200
    assert res_logout.json()["success"] is True

    # Verify session invalidated in DB
    conn = get_db()
    s = conn.execute("SELECT session_id FROM sessions WHERE session_id = ?", (sid,)).fetchone()
    conn.close()
    assert s is None

    # Subsequent request rejected
    res_after = client.get("/api/auth/me", cookies={"session_id": sid})
    assert res_after.json()["authenticated"] is False


def test_expired_sessions_are_rejected(client):
    """Expired session timestamps in database are rejected and cleaned up."""
    uid = "sec_test_expired"
    sid = _create_user(uid, "expired@sec.local")

    # Set expiry in the past
    conn = get_db()
    past_iso = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    conn.execute("UPDATE sessions SET expires_at = ? WHERE session_id = ?", (past_iso, sid))
    conn.commit()
    conn.close()

    res = client.get("/api/auth/me", cookies={"session_id": sid})
    assert res.json()["authenticated"] is False


def test_independent_sessions_for_different_users(client):
    """Different users receive independent sessions and cannot access each other's data."""
    sid_a = _create_user("sec_user_alpha", "alpha@sec.local")
    sid_b = _create_user("sec_user_beta", "beta@sec.local")

    res_a = client.get("/api/auth/me", cookies={"session_id": sid_a})
    res_b = client.get("/api/auth/me", cookies={"session_id": sid_b})

    assert res_a.json()["user"]["email"] == "alpha@sec.local"
    assert res_b.json()["user"]["email"] == "beta@sec.local"
    assert res_a.json()["user"]["id"] != res_b.json()["user"]["id"]


# ==============================================================================
# PHASE 4 & 5 REGRESSION TESTS: MANDATORY CALENDAR APPROVALS & AMBIGUITY
# ==============================================================================

@pytest.mark.asyncio
async def test_chat_requests_calendar_update_creates_approval():
    """Calendar update through chat/agent stages an approval and does NOT mutate DB immediately."""
    uid = "sec_test_cal_mut_1"
    _create_user(uid, "cal1@sec.local")

    conn = get_db()
    conn.execute(
        "INSERT INTO user_calendar_events (id, user_id, title, event_date, start_time, end_time, created_at) VALUES ('evt_update_1', ?, 'Sprint Planning', '2026-12-10', '10:00', '11:00', ?)",
        (uid, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()

    model_output = json.dumps({
        "action": {
            "tool": "update_calendar_event",
            "parameters": {"title": "Sprint Planning", "start_time": "14:00", "end_time": "15:00"}
        },
        "response": "Rescheduling Sprint Planning."
    })

    result = await execute_policy_gate_and_tools(model_output, uid, "main", kill_switch_active=False)
    assert result["approval_required"] is True
    assert result["tool_executed"] == "update_calendar_event"
    assert "Queued" in result["policy_decision"]
    appr_id = result["approval_id"]

    # Verify DB event is UNCHANGED before user approval
    conn = get_db()
    evt = conn.execute("SELECT start_time FROM user_calendar_events WHERE id = 'evt_update_1'").fetchone()
    assert evt["start_time"] == "10:00"

    # Verify approval record created
    appr = conn.execute("SELECT * FROM user_approvals WHERE id = ?", (appr_id,)).fetchone()
    assert appr is not None
    assert appr["type"] == "Calendar Update"
    assert appr["status"] == "pending"
    conn.close()


@pytest.mark.asyncio
async def test_chat_requests_calendar_deletion_creates_approval():
    """Calendar deletion through chat/agent stages an approval and does NOT mutate DB immediately."""
    uid = "sec_test_cal_mut_2"
    _create_user(uid, "cal2@sec.local")

    conn = get_db()
    conn.execute(
        "INSERT INTO user_calendar_events (id, user_id, title, event_date, start_time, end_time, created_at) VALUES ('evt_delete_1', ?, 'Quarterly Review', '2026-12-15', '09:00', '10:00', ?)",
        (uid, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()

    model_output = json.dumps({
        "action": {
            "tool": "delete_calendar_event",
            "parameters": {"title": "Quarterly Review"}
        },
        "response": "Canceling Quarterly Review."
    })

    result = await execute_policy_gate_and_tools(model_output, uid, "main", kill_switch_active=False)
    assert result["approval_required"] is True
    assert result["tool_executed"] == "delete_calendar_event"
    appr_id = result["approval_id"]

    # Verify event is NOT deleted before approval
    conn = get_db()
    evt = conn.execute("SELECT id FROM user_calendar_events WHERE id = 'evt_delete_1'").fetchone()
    assert evt is not None
    conn.close()


def test_user_rejects_calendar_approval(client):
    """Rejecting a calendar approval sets status to rejected and never executes the mutation."""
    uid = "sec_test_cal_mut_3"
    sid = _create_user(uid, "cal3@sec.local")

    conn = get_db()
    conn.execute(
        "INSERT INTO user_calendar_events (id, user_id, title, event_date, start_time, end_time, created_at) VALUES ('evt_rej_1', ?, 'Design Review', '2026-12-20', '11:00', '12:00', ?)",
        (uid, datetime.now(timezone.utc).isoformat())
    )
    appr_id = "appr_test_rej_1"
    draft = json.dumps({"action": "delete_calendar_event", "event_id": "evt_rej_1", "title": "Design Review"})
    conn.execute(
        "INSERT INTO user_approvals (id, user_id, type, target, subject, reason, risk_level, draft_content, status, created_at) VALUES (?, ?, 'Calendar Deletion', 'Design Review', 'Cancel Design Review', 'Reason', 'High', ?, 'pending', ?)",
        (appr_id, uid, draft, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()

    # User rejects
    res = client.post(f"/api/user/approvals/{appr_id}/action", json={"action": "reject"}, cookies={"session_id": sid})
    assert res.status_code == 200
    assert res.json()["status"] == "rejected"

    # Event must still exist in DB
    conn = get_db()
    evt = conn.execute("SELECT id FROM user_calendar_events WHERE id = 'evt_rej_1'").fetchone()
    assert evt is not None
    conn.close()


def test_unauthorized_user_cannot_act_on_others_calendar_approval(client):
    """User B cannot approve User A's calendar deletion."""
    sid_a = _create_user("sec_cal_user_a", "alice.calmut@sec.local")
    sid_b = _create_user("sec_cal_user_b", "bob.calmut@sec.local")

    conn = get_db()
    conn.execute(
        "INSERT INTO user_calendar_events (id, user_id, title, event_date, start_time, end_time, created_at) VALUES ('evt_sec_iso_1', 'sec_cal_user_a', 'Alice Secret Session', '2026-12-20', '11:00', '12:00', ?)",
        (datetime.now(timezone.utc).isoformat(),)
    )
    appr_id = "appr_alice_iso"
    draft = json.dumps({"action": "delete_calendar_event", "event_id": "evt_sec_iso_1", "title": "Alice Secret Session"})
    conn.execute(
        "INSERT INTO user_approvals (id, user_id, type, target, subject, reason, risk_level, draft_content, status, created_at) VALUES (?, 'sec_cal_user_a', 'Calendar Deletion', 'Target', 'Subject', 'Reason', 'High', ?, 'pending', ?)",
        (appr_id, draft, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()

    # Bob tries to approve Alice's item
    res = client.post(f"/api/user/approvals/{appr_id}/action", json={"action": "approve"}, cookies={"session_id": sid_b})
    assert res.status_code in [403, 404]

    # Alice's event was NOT deleted
    conn = get_db()
    evt = conn.execute("SELECT id FROM user_calendar_events WHERE id = 'evt_sec_iso_1'").fetchone()
    assert evt is not None
    conn.close()


def test_calendar_deletion_revalidation_when_event_deleted_before_approval(client):
    """If target event was deleted between approval creation and approval execution, abort safely."""
    uid = "sec_test_cal_mut_4"
    sid = _create_user(uid, "cal4@sec.local")

    conn = get_db()
    appr_id = "appr_test_ghost_event"
    draft = json.dumps({"action": "delete_calendar_event", "event_id": "evt_ghost_999", "title": "Ghost Event"})
    conn.execute(
        "INSERT INTO user_approvals (id, user_id, type, target, subject, reason, risk_level, draft_content, status, created_at) VALUES (?, ?, 'Calendar Deletion', 'Ghost Event', 'Cancel Ghost', 'Reason', 'High', ?, 'pending', ?)",
        (appr_id, uid, draft, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()

    # Approve for non-existent event
    res = client.post(f"/api/user/approvals/{appr_id}/action", json={"action": "approve"}, cookies={"session_id": sid})
    assert res.status_code == 404
    assert "not found or already deleted" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_ambiguous_calendar_deletion_refuses_auto_selection():
    """When multiple events match a vague title, system must NOT auto-select the first event."""
    uid = "sec_test_cal_ambig"
    _create_user(uid, "ambig@sec.local")

    conn = get_db()
    now_iso = datetime.now(timezone.utc).isoformat()
    # Insert two events with identical / matching titles on different times
    conn.execute("INSERT INTO user_calendar_events (id, user_id, title, event_date, start_time, end_time, created_at) VALUES ('evt_team_1', ?, 'Team Sync', '2026-12-01', '10:00', '11:00', ?)", (uid, now_iso))
    conn.execute("INSERT INTO user_calendar_events (id, user_id, title, event_date, start_time, end_time, created_at) VALUES ('evt_team_2', ?, 'Team Sync', '2026-12-02', '14:00', '15:00', ?)", (uid, now_iso))
    conn.commit()
    conn.close()

    model_output = json.dumps({
        "action": {
            "tool": "delete_calendar_event",
            "parameters": {"title": "Team Sync"}
        },
        "response": "Deleting Team Sync."
    })

    result = await execute_policy_gate_and_tools(model_output, uid, "main", kill_switch_active=False)
    # Must refuse ambiguous selection
    assert result["policy_decision"] == "Refused: Ambiguous Target Event"
    assert "multiple calendar events matched" in result["text"].lower()
    assert "10:00 - 11:00" in result["text"]
    assert "14:00 - 15:00" in result["text"]

    # Verify NEITHER event was deleted and NO approval was created
    conn = get_db()
    cnt = conn.execute("SELECT COUNT(*) as c FROM user_calendar_events WHERE user_id = ?", (uid,)).fetchone()["c"]
    apprs = conn.execute("SELECT COUNT(*) as c FROM user_approvals WHERE user_id = ?", (uid,)).fetchone()["c"]
    conn.close()
    assert cnt == 2
    assert apprs == 0


@pytest.mark.asyncio
async def test_calendar_mutation_no_matching_event_explains_clearly():
    """When no event matches, system explains clearly that no event was found."""
    uid = "sec_test_cal_none"
    _create_user(uid, "none@sec.local")

    model_output = json.dumps({
        "action": {
            "tool": "delete_calendar_event",
            "parameters": {"title": "Nonexistent Webinar"}
        },
        "response": "Deleting event."
    })

    result = await execute_policy_gate_and_tools(model_output, uid, "main", kill_switch_active=False)
    assert result["policy_decision"] == "Event Not Found"
    assert "could not find any calendar event matching" in result["text"].lower()


# ==============================================================================
# PHASE 6 REGRESSION TESTS: STRICT CORS ORIGIN ENFORCEMENT
# ==============================================================================

def test_cors_exact_production_origin_accepted(client):
    """Exact production origin https://deskagent.hacckthon.workers.dev is allowed with credentials."""
    resp = client.get(
        "/api/auth/status",
        headers={"Origin": "https://deskagent.hacckthon.workers.dev"}
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "https://deskagent.hacckthon.workers.dev"
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_cors_configured_development_origin_accepted(client):
    """Configured development origin http://localhost:5173 is allowed with credentials."""
    resp = client.get(
        "/api/auth/status",
        headers={"Origin": "http://localhost:5173"}
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_cors_random_workers_dev_origin_rejected(client):
    """Random *.workers.dev origin (e.g. attacker.workers.dev) receives no permissive CORS headers."""
    resp = client.get(
        "/api/auth/status",
        headers={"Origin": "https://random-attacker.workers.dev"}
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") is None
    assert resp.headers.get("access-control-allow-credentials") is None


def test_cors_random_pages_dev_origin_rejected(client):
    """Random *.pages.dev origin receives no permissive CORS headers."""
    resp = client.get(
        "/api/auth/status",
        headers={"Origin": "https://malicious.pages.dev"}
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") is None
    assert resp.headers.get("access-control-allow-credentials") is None


def test_cors_backend_worker_origin_rejected(client):
    """Backend Worker origin is not a frontend origin and receives no permissive CORS headers."""
    resp = client.get(
        "/api/auth/status",
        headers={"Origin": "https://deskagent-backend.hacckthon.workers.dev"}
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") is None
    assert resp.headers.get("access-control-allow-credentials") is None


def test_cors_malicious_subdomain_rejected(client):
    """Malicious subdomain attempting to impersonate production origin is rejected."""
    resp = client.get(
        "/api/auth/status",
        headers={"Origin": "https://attacker.deskagent.hacckthon.workers.dev"}
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") is None


def test_cors_misleading_suffix_rejected(client):
    """Origin containing production domain as a prefix with misleading suffix is rejected."""
    resp = client.get(
        "/api/auth/status",
        headers={"Origin": "https://deskagent.hacckthon.workers.dev.attacker.com"}
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") is None


def test_cors_missing_origin_handled_correctly(client):
    """Standard request without Origin header succeeds normally without CORS headers."""
    resp = client.get("/api/auth/status")
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") is None


def test_cors_credentials_allowed_only_for_trusted_origins(client):
    """Access-Control-Allow-Credentials is true for trusted origins and omitted for untrusted."""
    resp_trusted = client.get(
        "/api/auth/status",
        headers={"Origin": "https://deskagent.hacckthon.workers.dev"}
    )
    assert resp_trusted.headers.get("access-control-allow-credentials") == "true"

    resp_untrusted = client.get(
        "/api/auth/status",
        headers={"Origin": "https://untrusted-site.com"}
    )
    assert resp_untrusted.headers.get("access-control-allow-credentials") is None
    assert resp_untrusted.headers.get("access-control-allow-origin") is None


def test_cors_options_preflight_handling(client):
    """OPTIONS preflight for trusted origin returns allowed methods, headers and credentials."""
    resp = client.options(
        "/api/user/data",
        headers={
            "Origin": "https://deskagent.hacckthon.workers.dev",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, Authorization"
        }
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "https://deskagent.hacckthon.workers.dev"
    assert resp.headers.get("access-control-allow-credentials") == "true"
    assert "POST" in resp.headers.get("access-control-allow-methods", "")

    # Untrusted preflight receives no permissive CORS headers
    resp_untrusted = client.options(
        "/api/user/data",
        headers={
            "Origin": "https://attacker.workers.dev",
            "Access-Control-Request-Method": "POST",
        }
    )
    assert resp_untrusted.headers.get("access-control-allow-origin") is None
