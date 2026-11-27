import os
import sys
import unittest
import base64
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

# Ensure backend can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.main import app
from backend.database import get_db, init_db
from backend.security import generate_session_id, get_session_expiry, encrypt_token
from backend.google_service import _extract_message_body, _decode_body_part, _extract_attachments

class TestQAPhase2Inbox(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.conn = get_db()
        self.cursor = self.conn.cursor()

    def tearDown(self):
        self.cursor.execute("DELETE FROM user_tokens WHERE user_id LIKE 'usr_inbox_qa_%'")
        self.cursor.execute("DELETE FROM sessions WHERE user_id LIKE 'usr_inbox_qa_%'")
        self.cursor.execute("DELETE FROM users WHERE id LIKE 'usr_inbox_qa_%'")
        self.conn.commit()
        self.conn.close()

    def _create_user(self, user_id, email, name="Inbox QA Tester", gmail_connected=True):
        now_str = datetime.now(timezone.utc).isoformat()
        self.cursor.execute("""
            INSERT INTO users (id, email, name, picture, created_at)
            VALUES (?, ?, ?, 'https://example.com/avatar.png', ?)
            ON CONFLICT(id) DO UPDATE SET email = excluded.email, name = excluded.name
        """, (user_id, email, name, now_str))

        if gmail_connected:
            self.cursor.execute("""
                INSERT INTO user_tokens (user_id, access_token_encrypted, refresh_token_encrypted, token_expiry, scopes, gmail_connected, updated_at)
                VALUES (?, ?, ?, ?, 'openid email profile https://www.googleapis.com/auth/gmail.readonly', 1, ?)
                ON CONFLICT(user_id) DO UPDATE SET gmail_connected = 1
            """, (
                user_id,
                encrypt_token("mock_access_token_inbox"),
                encrypt_token("mock_refresh_token_inbox"),
                (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
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
    # 1. AUTHORIZATION & DISCONNECTED STATES
    # -------------------------------------------------------------
    def test_01_inbox_requires_authentication(self):
        """Verifies unauthorized calls to /api/gmail/messages return 401."""
        res = self.client.get("/api/gmail/messages")
        self.assertEqual(res.status_code, 401)
        self.assertIn("detail", res.json())

    def test_02_inbox_disconnected_state(self):
        """Verifies connected: False and empty list when user has not connected Gmail."""
        user_id = "usr_inbox_qa_disc"
        session_id = self._create_user(user_id, "disc@inbox.qa", gmail_connected=False)

        res = self.client.get("/api/gmail/messages", cookies={"session_id": session_id})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["connected"])
        self.assertEqual(data["messages"], [])
        self.assertIn("Connect your Gmail account", data["message"])

    def test_03_message_detail_requires_authentication(self):
        """Verifies unauthorized calls to /api/gmail/messages/{id} return 401."""
        res = self.client.get("/api/gmail/messages/msg_test_123")
        self.assertEqual(res.status_code, 401)

    # -------------------------------------------------------------
    # 2. EMAIL CONTENT EXTRACTION & SANITIZATION
    # -------------------------------------------------------------
    def test_04_html_sanitization_removes_scripts_and_styles(self):
        """Verifies that malicious scripts and CSS style blocks are stripped from email body."""
        html_payload = """
        <html>
            <head>
                <style>body { display: none; font-size: 50px; }</style>
                <script type="text/javascript">
                    window.location.href = "https://malicious-site.com/steal";
                </script>
            </head>
            <body>
                <h1>Project Deadline Notice</h1>
                <p>Please review the design document before <b>Friday 5 PM</b>.</p>
                <script>document.cookie = "stolen";</script>
            </body>
        </html>
        """
        payload = {
            "mimeType": "text/html",
            "body": {
                "data": base64.urlsafe_b64encode(html_payload.encode()).decode()
            }
        }
        body = _extract_message_body(payload)
        # Scripts and CSS must be completely absent
        self.assertNotIn("<script", body.lower())
        self.assertNotIn("window.location", body)
        self.assertNotIn("document.cookie", body)
        self.assertNotIn("display: none", body)
        # Clean plain text must be preserved
        self.assertIn("Project Deadline Notice", body)
        self.assertIn("Please review the design document before Friday 5 PM.", body)

    def test_05_multipart_mime_traversal(self):
        """Verifies multipart/alternative MIME email correctly extracts plain text."""
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {
                        "data": base64.urlsafe_b64encode(b"Plain text version of email with deadline tomorrow.").decode()
                    }
                },
                {
                    "mimeType": "text/html",
                    "body": {
                        "data": base64.urlsafe_b64encode(b"<p>HTML version</p>").decode()
                    }
                }
            ]
        }
        body = _extract_message_body(payload)
        self.assertIn("Plain text version of email with deadline tomorrow.", body)

    def test_06_attachment_metadata_extraction(self):
        """Verifies attachments are identified with filename, size, and mimeType without downloading."""
        payload = {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": base64.urlsafe_b64encode(b"Please see attached invoice.").decode()}
                },
                {
                    "filename": "Q4_Financial_Report.pdf",
                    "mimeType": "application/pdf",
                    "body": {"size": 245760, "attachmentId": "att_pdf_12345"}
                },
                {
                    "filename": "Receipt_Nov.png",
                    "mimeType": "image/png",
                    "body": {"size": 81920, "attachmentId": "att_png_67890"}
                }
            ]
        }
        attachments = _extract_attachments(payload)
        self.assertEqual(len(attachments), 2)
        self.assertEqual(attachments[0]["filename"], "Q4_Financial_Report.pdf")
        self.assertEqual(attachments[0]["size"], 245760)
        self.assertEqual(attachments[0]["mimeType"], "application/pdf")
        self.assertEqual(attachments[1]["filename"], "Receipt_Nov.png")

    # -------------------------------------------------------------
    # 3. MOCKED GMAIL API INTEGRATION TESTS
    # -------------------------------------------------------------
    @patch("backend.google_service.httpx.AsyncClient")
    def test_07_inbox_messages_parsing_and_unread_count(self, mock_client_cls):
        """Verifies parsing of sender, subject, date, snippet, and correct unread flag."""
        user_id = "usr_inbox_qa_parsed"
        session_id = self._create_user(user_id, "parsed@inbox.qa")

        mock_list_response = AsyncMock()
        mock_list_response.status_code = 200
        mock_list_response.json = MagicMock(return_value={
            "messages": [{"id": "msg_001"}, {"id": "msg_002"}],
            "nextPageToken": "token_page_2",
            "resultSizeEstimate": 2
        })

        mock_msg1_response = AsyncMock()
        mock_msg1_response.status_code = 200
        mock_msg1_response.json = MagicMock(return_value={
            "id": "msg_001",
            "threadId": "thread_001",
            "labelIds": ["INBOX", "UNREAD", "IMPORTANT"],
            "snippet": "Don't forget the board meeting deadline tomorrow.",
            "payload": {
                "headers": [
                    {"name": "From", "value": "Alice Manager <alice@company.org>"},
                    {"name": "Subject", "value": "Urgent: Q4 Strategy Deadline"},
                    {"name": "Date", "value": "Thu, 26 Nov 2026 14:00:00 +0000"}
                ]
            }
        })

        mock_msg2_response = AsyncMock()
        mock_msg2_response.status_code = 200
        mock_msg2_response.json = MagicMock(return_value={
            "id": "msg_002",
            "threadId": "thread_002",
            "labelIds": ["INBOX"],  # Read email
            "snippet": "Here is the weekly engineering newsletter.",
            "payload": {
                "headers": [
                    {"name": "From", "value": "Newsletter <news@techweekly.com>"},
                    {"name": "Subject", "value": "Tech Weekly Issue #42"},
                    {"name": "Date", "value": "Wed, 25 Nov 2026 10:00:00 +0000"}
                ]
            }
        })

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        async def mock_get(url, **kwargs):
            if url.endswith("/messages"):
                return mock_list_response
            elif url.endswith("/messages/msg_001"):
                return mock_msg1_response
            elif url.endswith("/messages/msg_002"):
                return mock_msg2_response
            return AsyncMock(status_code=404)

        mock_client.get.side_effect = mock_get
        mock_client_cls.return_value = mock_client

        res = self.client.get("/api/gmail/messages", cookies={"session_id": session_id})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["connected"])
        self.assertEqual(len(data["messages"]), 2)
        self.assertEqual(data["nextPageToken"], "token_page_2")

        # Verify Message 1 (Unread)
        m1 = data["messages"][0]
        self.assertEqual(m1["id"], "msg_001")
        self.assertEqual(m1["senderName"], "Alice Manager")
        self.assertEqual(m1["senderEmail"], "alice@company.org")
        self.assertEqual(m1["subject"], "Urgent: Q4 Strategy Deadline")
        self.assertTrue(m1["isUnread"])

        # Verify Message 2 (Read)
        m2 = data["messages"][1]
        self.assertEqual(m2["id"], "msg_002")
        self.assertEqual(m2["senderName"], "Newsletter")
        self.assertFalse(m2["isUnread"])

        # Verify Unread count calculation
        unread_count = sum(1 for m in data["messages"] if m["isUnread"])
        self.assertEqual(unread_count, 1)

    @patch("backend.google_service.httpx.AsyncClient")
    def test_08_message_detail_endpoint_mocked(self, mock_client_cls):
        """Verifies full message detail retrieval with sanitized body and recipient."""
        user_id = "usr_inbox_qa_detail"
        session_id = self._create_user(user_id, "detail@inbox.qa")

        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={
            "id": "msg_detail_100",
            "threadId": "thread_detail_100",
            "labelIds": ["INBOX"],
            "snippet": "Detailed contract attached.",
            "payload": {
                "headers": [
                    {"name": "From", "value": "Legal Department <legal@acme.corp>"},
                    {"name": "To", "value": "detail@inbox.qa"},
                    {"name": "Subject", "value": "Contract Agreement Final"},
                    {"name": "Date", "value": "Fri, 27 Nov 2026 09:30:00 +0000"}
                ],
                "mimeType": "text/plain",
                "body": {
                    "data": base64.urlsafe_b64encode(b"Please review and sign the contract agreement.").decode()
                }
            }
        })

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        res = self.client.get("/api/gmail/messages/msg_detail_100", cookies={"session_id": session_id})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["id"], "msg_detail_100")
        self.assertEqual(data["senderName"], "Legal Department")
        self.assertEqual(data["senderEmail"], "legal@acme.corp")
        self.assertEqual(data["recipient"], "detail@inbox.qa")
        self.assertEqual(data["subject"], "Contract Agreement Final")
        self.assertEqual(data["body"], "Please review and sign the contract agreement.")

    @patch("backend.google_service.httpx.AsyncClient")
    def test_09_message_not_found_returns_404(self, mock_client_cls):
        """Verifies 404 is returned when a message is deleted or not found in Gmail."""
        user_id = "usr_inbox_qa_404"
        session_id = self._create_user(user_id, "user404@inbox.qa")

        mock_resp = AsyncMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        res = self.client.get("/api/gmail/messages/deleted_msg_id", cookies={"session_id": session_id})
        self.assertEqual(res.status_code, 404)
        self.assertIn("not found or deleted", res.json()["detail"].lower())

    @patch("backend.google_service.httpx.AsyncClient")
    def test_10_empty_inbox_returns_clean_empty_list(self, mock_client_cls):
        """Verifies that an empty inbox returns connected: True with zero messages without errors."""
        user_id = "usr_inbox_qa_empty"
        session_id = self._create_user(user_id, "empty@inbox.qa")

        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={
            "resultSizeEstimate": 0
        })

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        res = self.client.get("/api/gmail/messages", cookies={"session_id": session_id})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["connected"])
        self.assertEqual(data["messages"], [])
        self.assertIsNone(data["nextPageToken"])

    @patch("backend.google_service.httpx.AsyncClient")
    def test_11_token_revoked_at_google_disconnects_gracefully(self, mock_client_cls):
        """Verifies that a 401 from Google API is caught and marks account as disconnected."""
        user_id = "usr_inbox_qa_revoked"
        session_id = self._create_user(user_id, "revoked@inbox.qa")

        mock_resp = AsyncMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        res = self.client.get("/api/gmail/messages", cookies={"session_id": session_id})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["connected"])
        self.assertIn("expired or was revoked", data["error"])

if __name__ == "__main__":
    unittest.main()
