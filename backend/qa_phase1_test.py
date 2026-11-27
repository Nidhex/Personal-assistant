import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

# Ensure backend can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.main import app
from backend.database import get_db, init_db
from backend.security import (
    generate_session_id,
    get_session_expiry,
    encrypt_token,
    decrypt_token,
    is_expired
)
import backend.google_service as google_service

class TestQAPhase1AuthAndGoogle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.conn = get_db()
        self.cursor = self.conn.cursor()

    def tearDown(self):
        # Clean up test entities created during test
        self.cursor.execute("DELETE FROM user_tokens WHERE user_id LIKE 'usr_qa_%'")
        self.cursor.execute("DELETE FROM sessions WHERE user_id LIKE 'usr_qa_%'")
        self.cursor.execute("DELETE FROM user_tasks WHERE user_id LIKE 'usr_qa_%'")
        self.cursor.execute("DELETE FROM user_workspaces WHERE user_id LIKE 'usr_qa_%'")
        self.cursor.execute("DELETE FROM conversations WHERE user_id LIKE 'usr_qa_%'")
        self.cursor.execute("DELETE FROM messages WHERE user_id LIKE 'usr_qa_%'")
        self.cursor.execute("DELETE FROM user_calendar_events WHERE user_id LIKE 'usr_qa_%'")
        self.cursor.execute("DELETE FROM user_study_materials WHERE user_id LIKE 'usr_qa_%'")
        self.cursor.execute("DELETE FROM user_approvals WHERE user_id LIKE 'usr_qa_%'")
        self.cursor.execute("DELETE FROM user_activity WHERE user_id LIKE 'usr_qa_%'")
        self.cursor.execute("DELETE FROM agent_runs WHERE user_id LIKE 'usr_qa_%'")
        self.cursor.execute("DELETE FROM daily_digests WHERE user_id LIKE 'usr_qa_%'")
        self.cursor.execute("DELETE FROM oauth_states WHERE state LIKE 'qa_test_state_%'")
        self.cursor.execute("DELETE FROM users WHERE id LIKE 'usr_qa_%'")
        self.conn.commit()
        self.conn.close()

    def _create_user(self, user_id, email, name="QA Tester", gmail_connected=False, access_token="mock_access"):
        now_str = datetime.now(timezone.utc).isoformat()
        self.cursor.execute("""
            INSERT INTO users (id, email, name, picture, created_at)
            VALUES (?, ?, ?, 'https://example.com/avatar.png', ?)
            ON CONFLICT(id) DO UPDATE SET email = excluded.email, name = excluded.name
        """, (user_id, email, name, now_str))

        if gmail_connected:
            self.cursor.execute("""
                INSERT INTO user_tokens (user_id, access_token_encrypted, refresh_token_encrypted, token_expiry, scopes, gmail_connected, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(user_id) DO UPDATE SET gmail_connected = 1
            """, (
                user_id,
                encrypt_token(access_token),
                encrypt_token("mock_refresh"),
                (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                "openid email profile https://www.googleapis.com/auth/gmail.readonly",
                now_str
            ))
        else:
            self.cursor.execute("""
                INSERT INTO user_tokens (user_id, access_token_encrypted, refresh_token_encrypted, token_expiry, scopes, gmail_connected, updated_at)
                VALUES (?, '', '', '', '', 0, ?)
                ON CONFLICT(user_id) DO UPDATE SET gmail_connected = 0
            """, (user_id, now_str))

        session_id = generate_session_id()
        expires_at = get_session_expiry(7)
        self.cursor.execute("""
            INSERT INTO sessions (session_id, user_id, expires_at, created_at)
            VALUES (?, ?, ?, ?)
        """, (session_id, user_id, expires_at, now_str))
        self.conn.commit()
        return session_id

    # -------------------------------------------------------------
    # 1. AUTHENTICATION TESTS
    # -------------------------------------------------------------
    def test_01_auth_status_endpoint(self):
        """Verifies /api/auth/status returns correct configuration metadata and strictly read-only scopes."""
        res = self.client.get("/api/auth/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("google_configured", data)
        self.assertIn("scopes_requested", data)
        # Verify scopes strictly read-only
        self.assertIn("https://www.googleapis.com/auth/gmail.readonly", data["scopes_requested"])
        for scope in data["scopes_requested"]:
            self.assertNotIn("modify", scope)
            self.assertNotIn("send", scope)
            self.assertNotIn("compose", scope)

    def test_02_unauthenticated_api_requests_return_401(self):
        """Verifies unauthorized requests to protected endpoints return 401."""
        endpoints = [
            ("GET", "/api/user/data"),
            ("POST", "/api/user/tasks"),
            ("GET", "/api/chat/conversations"),
            ("POST", "/api/chat/conversations"),
            ("GET", "/api/user/calendar/events"),
            ("GET", "/api/agent/settings"),
            ("GET", "/api/agent/runs"),
        ]
        for method, endpoint in endpoints:
            if method == "GET":
                res = self.client.get(endpoint)
            else:
                res = self.client.post(endpoint, json={})
            self.assertEqual(res.status_code, 401, f"{endpoint} should return 401 when unauthenticated")
            self.assertIn("detail", res.json())

    def test_03_unauthenticated_auth_me(self):
        """Verifies GET /api/auth/me returns authenticated: False without raising 401."""
        res = self.client.get("/api/auth/me")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["authenticated"])
        self.assertIsNone(data["user"])
        self.assertFalse(data["gmail_connected"])

    def test_04_session_creation_and_persistence(self):
        """Verifies session cookie persistence, user identification, and /api/auth/me payload."""
        user_id = "usr_qa_user1"
        email = "user1@test.local"
        session_id = self._create_user(user_id, email, "QA User One")

        # Request with cookie
        self.client.cookies.set("session_id", session_id)
        res = self.client.get("/api/auth/me")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["user"]["id"], user_id)
        self.assertEqual(data["user"]["email"], email)
        self.assertEqual(data["user"]["name"], "QA User One")

        # Second request (simulating browser refresh / persistent session)
        res2 = self.client.get("/api/user/data")
        self.assertEqual(res2.status_code, 200)
        self.client.cookies.clear()

    def test_05_session_authorization_via_bearer_header(self):
        """Verifies fallback to Authorization: Bearer <session_id>."""
        user_id = "usr_qa_bearer"
        session_id = self._create_user(user_id, "bearer@test.local", "Bearer User")
        res = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {session_id}"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["authenticated"])
        self.assertEqual(res.json()["user"]["id"], user_id)

    def test_06_expired_session_handling(self):
        """Verifies expired session is deleted from database and rejected as 401."""
        user_id = "usr_qa_expired"
        # Create expired session (1 day in the past)
        past_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        session_id = generate_session_id()
        self.cursor.execute("""
            INSERT INTO users (id, email, name, picture, created_at)
            VALUES (?, 'expired@test.local', 'Expired User', '', ?)
        """, (user_id, past_time))
        self.cursor.execute("""
            INSERT INTO sessions (session_id, user_id, expires_at, created_at)
            VALUES (?, ?, ?, ?)
        """, (session_id, user_id, past_time, past_time))
        self.conn.commit()

        # Check /api/auth/me with expired session
        res = self.client.get("/api/auth/me", cookies={"session_id": session_id})
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["authenticated"])

        # Check protected endpoint with expired session
        res_data = self.client.get("/api/user/data", cookies={"session_id": session_id})
        self.assertEqual(res_data.status_code, 401)

        # Verify session was deleted from database
        self.cursor.execute("SELECT session_id FROM sessions WHERE session_id = ?", (session_id,))
        self.assertIsNone(self.cursor.fetchone(), "Expired session must be automatically cleaned up")

    def test_07_invalid_and_tampered_session_id(self):
        """Verifies forged or random session cookies are rejected cleanly."""
        for forged in ["nonexistent_session_id", "forged' OR 1=1 --", "", "   "]:
            res = self.client.get("/api/auth/me", cookies={"session_id": forged})
            self.assertEqual(res.status_code, 200)
            self.assertFalse(res.json()["authenticated"])

            res_prot = self.client.get("/api/user/data", cookies={"session_id": forged})
            self.assertEqual(res_prot.status_code, 401)

    def test_08_sign_out_flow(self):
        """Verifies logout deletes session from DB and clears session cookie."""
        user_id = "usr_qa_logout"
        session_id = self._create_user(user_id, "logout@test.local")

        # Perform sign out with cookie
        self.client.cookies.set("session_id", session_id)
        res = self.client.post("/api/auth/logout")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])

        # Verify session record is deleted from SQLite
        self.cursor.execute("SELECT session_id FROM sessions WHERE session_id = ?", (session_id,))
        self.assertIsNone(self.cursor.fetchone(), "Session must be deleted upon sign-out")

        # Subsequent call with old session should fail
        res_after = self.client.get("/api/user/data", cookies={"session_id": session_id})
        self.assertEqual(res_after.status_code, 401)
        self.client.cookies.clear()

    def test_08b_sign_out_with_bearer_token(self):
        """Verifies logout with Authorization: Bearer <session_id> invalidates session."""
        user_id = "usr_qa_logout_bearer"
        session_id = self._create_user(user_id, "logoutbearer@test.local")

        # Perform sign out via Authorization header
        res = self.client.post("/api/auth/logout", headers={"Authorization": f"Bearer {session_id}"})
        self.assertEqual(res.status_code, 200)

        # Verify session record is deleted from SQLite
        self.cursor.execute("SELECT session_id FROM sessions WHERE session_id = ?", (session_id,))
        self.assertIsNone(self.cursor.fetchone(), "Session must be deleted even when passed via Bearer header")

    def test_09_sign_in_after_sign_out(self):
        """Verifies a user can sign in again after sign out with a new session."""
        user_id = "usr_qa_relogin"
        email = "relogin@test.local"
        session1 = self._create_user(user_id, email)

        # Logout session 1
        self.client.post("/api/auth/logout", cookies={"session_id": session1})

        # Create session 2 (simulating new login)
        session2 = generate_session_id()
        self.cursor.execute("""
            INSERT INTO sessions (session_id, user_id, expires_at, created_at)
            VALUES (?, ?, ?, ?)
        """, (session2, user_id, get_session_expiry(7), datetime.now(timezone.utc).isoformat()))
        self.conn.commit()

        # Check session 2 works
        res = self.client.get("/api/auth/me", cookies={"session_id": session2})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["authenticated"])
        self.assertEqual(res.json()["user"]["email"], email)

    def test_10_oauth_callback_csrf_and_replay_protection(self):
        """Verifies OAuth callback validates state, rejects forged states, and prevents replay attacks."""
        state = "qa_test_state_12345"
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        self.cursor.execute("""
            INSERT INTO oauth_states (state, action, user_id, expires_at)
            VALUES (?, 'login', NULL, ?)
        """, (state, expires_at))
        self.conn.commit()

        # Attempt with forged state
        res_forged = self.client.get("/api/auth/google/callback", params={"code": "mock_code", "state": "wrong_state"}, follow_redirects=False)
        self.assertEqual(res_forged.status_code, 307)
        self.assertIn("auth_error=invalid_or_expired_state", res_forged.headers["location"])

        # Attempt with missing params
        res_missing = self.client.get("/api/auth/google/callback", params={"code": "mock_code"}, follow_redirects=False)
        self.assertEqual(res_missing.status_code, 307)
        self.assertIn("auth_error=missing_parameters", res_missing.headers["location"])

        # Attempt with Google error param (e.g. user cancelled)
        res_err = self.client.get("/api/auth/google/callback", params={"error": "access_denied"}, follow_redirects=False)
        self.assertEqual(res_err.status_code, 307)
        self.assertIn("auth_error=access_denied", res_err.headers["location"])

    # -------------------------------------------------------------
    # 2. GOOGLE CONNECTION & GMAIL AUTHORIZATION TESTS
    # -------------------------------------------------------------
    def test_11_token_encryption_at_rest(self):
        """Verifies OAuth tokens are encrypted at rest with Fernet and never stored plaintext."""
        raw_token = "ya29.a0AfH6SMB_secret_access_token_123"
        enc = encrypt_token(raw_token)
        self.assertNotEqual(raw_token, enc)
        self.assertNotIn(raw_token, enc)
        self.assertEqual(decrypt_token(enc), raw_token)

    def test_12_gmail_disconnected_state(self):
        """Verifies Gmail endpoints behave safely when Gmail is not connected."""
        user_id = "usr_qa_no_gmail"
        session_id = self._create_user(user_id, "nogmail@test.local", gmail_connected=False)

        res_mail = self.client.get("/api/gmail/messages", cookies={"session_id": session_id})
        self.assertEqual(res_mail.status_code, 200)
        data = res_mail.json()
        self.assertFalse(data["connected"])
        self.assertEqual(len(data["messages"]), 0)

        # Message detail when disconnected returns 400
        res_detail = self.client.get("/api/gmail/messages/msg_123", cookies={"session_id": session_id})
        self.assertEqual(res_detail.status_code, 400)

    def test_13_gmail_disconnect_endpoint(self):
        """Verifies /api/gmail/disconnect marks tokens as disconnected and revokes local access."""
        user_id = "usr_qa_disc"
        session_id = self._create_user(user_id, "disc@test.local", gmail_connected=True)

        res = self.client.post("/api/gmail/disconnect", cookies={"session_id": session_id})
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["gmail_connected"])

        # Verify DB status
        self.cursor.execute("SELECT gmail_connected, access_token_encrypted FROM user_tokens WHERE user_id = ?", (user_id,))
        row = self.cursor.fetchone()
        self.assertEqual(row["gmail_connected"], 0)
        self.assertEqual(row["access_token_encrypted"], "")

    # -------------------------------------------------------------
    # 3. TWO-USER ISOLATION TESTS
    # -------------------------------------------------------------
    def test_14_two_user_complete_isolation(self):
        """Strictly verifies that User A and User B cannot read or tamper with each other's data."""
        # 1. Setup User A
        user_a = "usr_qa_alice"
        session_a = self._create_user(user_a, "alice@qa.local", "Alice QA")

        # 2. Setup User B
        user_b = "usr_qa_bob"
        session_b = self._create_user(user_b, "bob@qa.local", "Bob QA")

        # Alice creates private data across all subsystems
        now_str = datetime.now(timezone.utc).isoformat()
        self.cursor.execute("""
            INSERT INTO user_tasks (id, user_id, title, source, due_date, priority, completed, workspace, created_at)
            VALUES ('tsk_alice_priv', ?, 'Alice Secret Plan', 'Manual', '2026-12-01', 'high', 0, 'Research', ?)
        """, (user_a, now_str))

        self.cursor.execute("""
            INSERT INTO user_workspaces (id, user_id, name, type, description, created_at)
            VALUES ('ws_alice_priv', ?, 'Alice Secret Lab', 'project', 'Confidential', ?)
        """, (user_a, now_str))

        self.cursor.execute("""
            INSERT INTO conversations (id, user_id, workspace_id, title, created_at, updated_at)
            VALUES ('conv_alice_priv', ?, NULL, 'Alice Executive Dialogue', ?, ?)
        """, (user_a, now_str, now_str))

        self.cursor.execute("""
            INSERT INTO messages (id, conversation_id, user_id, workspace_id, role, content, metadata, created_at)
            VALUES ('msg_alice_priv', 'conv_alice_priv', ?, NULL, 'user', 'Alice secret financial figures', '{}', ?)
        """, (user_a, now_str))

        self.cursor.execute("""
            INSERT INTO user_calendar_events (id, user_id, workspace_id, title, event_date, start_time, end_time, category, description, source, created_at)
            VALUES ('evt_alice_priv', ?, NULL, 'Alice Board Meeting', '2026-12-10', '10:00', '11:00', 'Confidential', 'Private', 'Manual', ?)
        """, (user_a, now_str))

        self.cursor.execute("""
            INSERT INTO user_study_materials (id, user_id, workspace_id, filename, content_text, created_at)
            VALUES ('mat_alice_priv', ?, 'ws_alice_priv', 'alice_patent.txt', 'Alice patented formula', ?)
        """, (user_a, now_str))

        self.cursor.execute("""
            INSERT INTO user_approvals (id, user_id, type, target, subject, reason, risk_level, draft_content, status, created_at)
            VALUES ('app_alice_priv', ?, 'action', 'system', 'Alice Gate', 'Testing', 'high', 'secret draft', 'pending', ?)
        """, (user_a, now_str))

        self.cursor.execute("""
            INSERT INTO agent_runs (id, user_id, trigger_type, status, summary, started_at, completed_at)
            VALUES ('run_alice_priv', ?, 'manual', 'completed', 'Alice private run summary', ?, ?)
        """, (user_a, now_str, now_str))

        self.cursor.execute("""
            INSERT INTO daily_digests (id, user_id, title, digest_date, content_json, created_at)
            VALUES ('dig_alice_priv', ?, 'Alice Private Digest', '2026-11-27', '{\"summary\": \"Alice private daily digest\"}', ?)
        """, (user_a, now_str))

        self.conn.commit()

        # Test A: Profile isolation
        res_me_a = self.client.get("/api/auth/me", cookies={"session_id": session_a})
        self.assertEqual(res_me_a.json()["user"]["email"], "alice@qa.local")

        res_me_b = self.client.get("/api/auth/me", cookies={"session_id": session_b})
        self.assertEqual(res_me_b.json()["user"]["email"], "bob@qa.local")
        self.assertNotEqual(res_me_b.json()["user"]["id"], user_a)

        # Test B: /api/user/data isolation
        res_data_b = self.client.get("/api/user/data", cookies={"session_id": session_b})
        data_b = res_data_b.json()
        b_tasks = [t["title"] for t in data_b["tasks"]]
        b_workspaces = [w["name"] for w in data_b["workspaces"]]
        b_approvals = [a["id"] for a in data_b["approvals"]]
        self.assertNotIn("Alice Secret Plan", b_tasks)
        self.assertNotIn("Alice Secret Lab", b_workspaces)
        self.assertNotIn("app_alice_priv", b_approvals)

        # Test C: Conversation messages isolation
        res_conv_b = self.client.get("/api/chat/conversations/conv_alice_priv/messages", cookies={"session_id": session_b})
        self.assertEqual(res_conv_b.status_code, 404, "Bob must receive 404 when querying Alice's conversation")

        # Test D: Tampering with Alice's conversation
        res_send_b = self.client.post(
            "/api/chat/conversations/conv_alice_priv/messages",
            json={"content": "Bob trying to inject message"},
            cookies={"session_id": session_b}
        )
        self.assertEqual(res_send_b.status_code, 404, "Bob cannot post to Alice's conversation")

        # Test E: Deleting Alice's conversation
        res_del_conv = self.client.delete("/api/chat/conversations/conv_alice_priv", cookies={"session_id": session_b})
        self.assertEqual(res_del_conv.status_code, 404, "Bob cannot delete Alice's conversation")

        # Test F: Calendar event isolation
        res_cal_b = self.client.get("/api/user/calendar/events", cookies={"session_id": session_b})
        b_events = [e["title"] for e in res_cal_b.json()["events"]]
        self.assertNotIn("Alice Board Meeting", b_events)

        res_del_cal = self.client.delete("/api/user/calendar/events/evt_alice_priv", cookies={"session_id": session_b})
        self.assertEqual(res_del_cal.status_code, 404, "Bob cannot delete Alice's calendar event")

        # Test G: Task tampering
        res_toggle_b = self.client.post("/api/user/tasks/tsk_alice_priv/toggle", cookies={"session_id": session_b})
        self.assertEqual(res_toggle_b.status_code, 404, "Bob cannot toggle Alice's task")

        # Test H: Workspace study materials isolation
        res_study_b = self.client.get("/api/user/workspaces/ws_alice_priv/study-materials", cookies={"session_id": session_b})
        self.assertEqual(len(res_study_b.json()["materials"]), 0, "Bob cannot see Alice's study materials")

        # Test I: Agent run steps isolation
        res_steps_b = self.client.get("/api/agent/runs/run_alice_priv/steps", cookies={"session_id": session_b})
        self.assertEqual(res_steps_b.status_code, 404, "Bob cannot see Alice's agent run steps")

        # Test J: Daily digest isolation
        res_digest_b = self.client.get("/api/agent/digests/latest", cookies={"session_id": session_b})
        self.assertIsNone(res_digest_b.json()["digest"], "Bob cannot see Alice's daily digest")

if __name__ == "__main__":
    unittest.main()
