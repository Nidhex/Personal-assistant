"""
Regression tests for Stage 3: Gmail Worker HTTP Compatibility Remediation.
Verifies that Gmail draft operations (create_gmail_draft, reconcile_gmail_draft)
execute seamlessly across both:
1. Cloudflare Python Worker runtime (using Cloudflare-compatible HTTP adapter)
2. Local Python / development runtime (using httpx.AsyncClient)
"""
import unittest
import base64
import email
import json
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from email import policy

from backend.http_client import WorkerHttpResponse
from backend.google_service import create_gmail_draft, reconcile_gmail_draft
import backend.google_service as gs


class TestGmailWorkerCompatibility(unittest.TestCase):
    def setUp(self):
        self.mock_user_id = "usr_stage3_worker_test"
        self.mock_token = "ya29.stage3_super_secret_mock_oauth_token_xyz123"

    def _decode_raw_mime(self, raw_b64: str) -> email.message.EmailMessage:
        raw_bytes = base64.urlsafe_b64decode(raw_b64)
        return email.message_from_bytes(raw_bytes, policy=policy.default)

    # --------------------------------------------------------------------------
    # 1. Successful Gmail draft creation via Worker HTTP adapter
    # --------------------------------------------------------------------------
    def test_01_create_gmail_draft_success_worker_adapter_path(self):
        """Verifies that in Worker mode, create_gmail_draft routes through http_post without invoking httpx.AsyncClient."""
        mock_response = WorkerHttpResponse(
            status_code=200,
            text='{"id": "draft_worker_created_001", "message": {"id": "msg_001"}}',
            json_data={"id": "draft_worker_created_001", "message": {"id": "msg_001"}},
            headers={"content-type": "application/json"}
        )

        mock_http_post = AsyncMock(return_value=mock_response)

        with patch("backend.google_service.get_valid_access_token", new=AsyncMock(return_value=self.mock_token)), \
             patch.object(gs, "HAS_WORKER_FETCH", True), \
             patch("backend.google_service.http_post", new=mock_http_post), \
             patch("httpx.AsyncClient", side_effect=AssertionError("httpx.AsyncClient must not be called in Worker mode")):

            draft_id = asyncio.run(create_gmail_draft(
                user_id=self.mock_user_id,
                to="recipient@example.com",
                subject="Worker Draft Subject",
                body="Hello from the Cloudflare Worker adapter!",
                approval_id="appr_worker_draft_01"
            ))

            self.assertEqual(draft_id, "draft_worker_created_001")
            mock_http_post.assert_awaited_once()

            # Verify request URL, headers, and payload structure
            call_args = mock_http_post.await_args
            url = call_args[0][0] if call_args[0] else call_args.kwargs.get("url")
            headers = call_args.kwargs.get("headers", {})
            json_data = call_args.kwargs.get("json_data", {})
            timeout = call_args.kwargs.get("timeout")

            self.assertEqual(url, "https://gmail.googleapis.com/gmail/v1/users/me/drafts")
            self.assertEqual(headers.get("Authorization"), f"Bearer {self.mock_token}")
            self.assertEqual(headers.get("Content-Type"), "application/json")
            self.assertEqual(timeout, 10.0)

            # Verify MIME structure inside raw payload
            raw_b64 = json_data.get("message", {}).get("raw")
            self.assertTrue(bool(raw_b64))
            mime_msg = self._decode_raw_mime(raw_b64)
            self.assertEqual(mime_msg["To"], "recipient@example.com")
            self.assertEqual(mime_msg["Subject"], "Worker Draft Subject")
            self.assertEqual(mime_msg["X-Assistant-Approval-Id"], "appr_worker_draft_01")
            self.assertIn("Hello from the Cloudflare Worker adapter!", mime_msg.get_content())

    # --------------------------------------------------------------------------
    # 2. Successful Gmail draft creation via Local development path
    # --------------------------------------------------------------------------
    def test_02_create_gmail_draft_success_local_adapter_path(self):
        """Verifies that in local development mode (HAS_WORKER_FETCH=False), httpx.AsyncClient path succeeds."""
        mock_httpx_resp = MagicMock()
        mock_httpx_resp.status_code = 200
        mock_httpx_resp.json.return_value = {"id": "draft_local_created_002"}
        mock_httpx_resp.text = '{"id": "draft_local_created_002"}'

        client_inst = AsyncMock()
        client_inst.post.return_value = mock_httpx_resp
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=client_inst)
        cm.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.google_service.get_valid_access_token", new=AsyncMock(return_value=self.mock_token)), \
             patch.object(gs, "HAS_WORKER_FETCH", False), \
             patch("backend.google_service.httpx.AsyncClient", return_value=cm):

            draft_id = asyncio.run(create_gmail_draft(
                user_id=self.mock_user_id,
                to="local_user@example.com",
                subject="Local Draft Subject",
                body="Testing local httpx adapter path.",
                approval_id="appr_local_draft_02"
            ))

            self.assertEqual(draft_id, "draft_local_created_002")
            client_inst.post.assert_awaited_once()

    # --------------------------------------------------------------------------
    # 3. Authorization header forwarding and security against token leakage
    # --------------------------------------------------------------------------
    def test_03_auth_header_forwarding_and_no_token_leakage_on_failure(self):
        """Verifies that Authorization header is forwarded and access token is never leaked in exception messages."""
        # Simulate network error in Worker HTTP adapter
        mock_http_post = AsyncMock(side_effect=Exception(f"Socket connection error to host with auth Bearer {self.mock_token}"))

        with patch("backend.google_service.get_valid_access_token", new=AsyncMock(return_value=self.mock_token)), \
             patch.object(gs, "HAS_WORKER_FETCH", True), \
             patch("backend.google_service.http_post", new=mock_http_post):

            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(create_gmail_draft(
                    user_id=self.mock_user_id,
                    to="user@example.com",
                    subject="Leak Test",
                    body="Testing credential protection.",
                    approval_id="appr_leak_03"
                ))

            err_msg = str(ctx.exception)
            # The error message must NEVER leak the secret token
            self.assertNotIn(self.mock_token, err_msg)
            self.assertNotIn("Bearer", err_msg)
            self.assertIn("Gmail API network error or timeout during draft creation", err_msg)

    # --------------------------------------------------------------------------
    # 4. Gmail API non-success HTTP status codes (400, 401, 403, 500)
    # --------------------------------------------------------------------------
    def test_04_create_gmail_draft_api_error_responses(self):
        """Verifies safe and precise error handling for 400, 401, 403, and 500 status codes."""
        status_cases = [
            (400, "Gmail draft creation failed (400)."),
            (401, "Gmail draft creation failed (401)."),
            (403, "Gmail compose permission missing. Please re-authorize Google OAuth to grant gmail.compose."),
            (500, "Gmail draft creation failed (500)."),
        ]

        for code, expected_message in status_cases:
            mock_response = WorkerHttpResponse(
                status_code=code,
                text=f'{{"error": {{"code": {code}, "message": "API error response with sensitive internals"}}}}',
                json_data={"error": {"code": code, "message": "API error response with sensitive internals"}}
            )
            mock_http_post = AsyncMock(return_value=mock_response)

            with patch("backend.google_service.get_valid_access_token", new=AsyncMock(return_value=self.mock_token)), \
                 patch.object(gs, "HAS_WORKER_FETCH", True), \
                 patch("backend.google_service.http_post", new=mock_http_post):

                with self.assertRaises(Exception) as ctx:
                    asyncio.run(create_gmail_draft(
                        user_id=self.mock_user_id,
                        to="user@example.com",
                        subject=f"Status {code} test",
                        body="Testing status codes."
                    ))

                self.assertEqual(str(ctx.exception), expected_message)
                self.assertNotIn("sensitive internals", str(ctx.exception))

    # --------------------------------------------------------------------------
    # 5. Missing or invalid access token
    # --------------------------------------------------------------------------
    def test_05_create_gmail_draft_missing_access_token(self):
        """Verifies that create_gmail_draft fails immediately if no valid access token exists without dispatching HTTP requests."""
        mock_http_post = AsyncMock()

        with patch("backend.google_service.get_valid_access_token", new=AsyncMock(return_value=None)), \
             patch.object(gs, "HAS_WORKER_FETCH", True), \
             patch("backend.google_service.http_post", new=mock_http_post):

            with self.assertRaises(Exception) as ctx:
                asyncio.run(create_gmail_draft(
                    user_id=self.mock_user_id,
                    to="user@example.com",
                    subject="No Token Test",
                    body="Body"
                ))

            self.assertIn("Google account not connected or token expired", str(ctx.exception))
            mock_http_post.assert_not_called()

    # --------------------------------------------------------------------------
    # 6. Uncertain draft outcome when API returns no draft ID
    # --------------------------------------------------------------------------
    def test_06_create_gmail_draft_uncertain_outcome_no_id(self):
        """Verifies that empty draft ID returns RuntimeError('UNCERTAIN_DRAFT_OUTCOME: ...')."""
        mock_response = WorkerHttpResponse(
            status_code=200,
            text='{"message": {"id": "only_message_id_no_draft_id"}}',
            json_data={"message": {"id": "only_message_id_no_draft_id"}}
        )

        with patch("backend.google_service.get_valid_access_token", new=AsyncMock(return_value=self.mock_token)), \
             patch.object(gs, "HAS_WORKER_FETCH", True), \
             patch("backend.google_service.http_post", new=AsyncMock(return_value=mock_response)):

            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(create_gmail_draft(
                    user_id=self.mock_user_id,
                    to="user@example.com",
                    subject="Uncertain Test",
                    body="Body"
                ))

            self.assertIn("UNCERTAIN_DRAFT_OUTCOME", str(ctx.exception))

    # --------------------------------------------------------------------------
    # 7. Reconcile Gmail draft via Worker HTTP adapter
    # --------------------------------------------------------------------------
    def test_07_reconcile_gmail_draft_worker_adapter_success(self):
        """Verifies that reconcile_gmail_draft uses http_get in Worker mode and successfully adopts matching draft."""
        list_response = WorkerHttpResponse(
            status_code=200,
            text='{"drafts": [{"id": "draft_worker_reconcile_42"}]}',
            json_data={"drafts": [{"id": "draft_worker_reconcile_42"}]}
        )

        detail_response = WorkerHttpResponse(
            status_code=200,
            text='{"id": "draft_worker_reconcile_42"}',
            json_data={
                "id": "draft_worker_reconcile_42",
                "message": {
                    "payload": {
                        "headers": [
                            {"name": "X-Assistant-Approval-Id", "value": "appr_reconcile_42"},
                            {"name": "To", "value": "client@business.org"},
                            {"name": "Subject", "value": "Meeting Notes Followup"}
                        ],
                        "body": {
                            "data": base64.urlsafe_b64encode(b"Here are the meeting notes as discussed.").decode("ascii")
                        }
                    }
                }
            }
        )

        mock_http_get = AsyncMock(side_effect=[list_response, detail_response])

        with patch("backend.google_service.get_valid_access_token", new=AsyncMock(return_value=self.mock_token)), \
             patch.object(gs, "HAS_WORKER_FETCH", True), \
             patch("backend.google_service.http_get", new=mock_http_get), \
             patch("httpx.AsyncClient", side_effect=AssertionError("httpx.AsyncClient must not be called in Worker mode")):

            reconciled_id = asyncio.run(reconcile_gmail_draft(
                user_id=self.mock_user_id,
                approval_id="appr_reconcile_42",
                expected_to="client@business.org",
                expected_subject="Meeting Notes Followup",
                expected_body="Here are the meeting notes as discussed."
            ))

            self.assertEqual(reconciled_id, "draft_worker_reconcile_42")
            self.assertEqual(mock_http_get.await_count, 2)

    # --------------------------------------------------------------------------
    # 8. Reconcile Gmail draft returns None on marker or body mismatch
    # --------------------------------------------------------------------------
    def test_08_reconcile_gmail_draft_mismatch_returns_none(self):
        """Verifies that reconcile_gmail_draft returns None if approval marker or body differs."""
        list_response = WorkerHttpResponse(
            status_code=200,
            text='{"drafts": [{"id": "draft_mismatch_99"}]}',
            json_data={"drafts": [{"id": "draft_mismatch_99"}]}
        )

        # Different body than expected
        detail_response = WorkerHttpResponse(
            status_code=200,
            text='{"id": "draft_mismatch_99"}',
            json_data={
                "id": "draft_mismatch_99",
                "message": {
                    "payload": {
                        "headers": [
                            {"name": "X-Assistant-Approval-Id", "value": "appr_test_99"},
                            {"name": "To", "value": "target@domain.com"},
                            {"name": "Subject", "value": "Correct Subject"}
                        ],
                        "body": {
                            "data": base64.urlsafe_b64encode(b"Altered body by third party").decode("ascii")
                        }
                    }
                }
            }
        )

        mock_http_get = AsyncMock(side_effect=[list_response, detail_response])

        with patch("backend.google_service.get_valid_access_token", new=AsyncMock(return_value=self.mock_token)), \
             patch.object(gs, "HAS_WORKER_FETCH", True), \
             patch("backend.google_service.http_get", new=mock_http_get):

            reconciled = asyncio.run(reconcile_gmail_draft(
                user_id=self.mock_user_id,
                approval_id="appr_test_99",
                expected_to="target@domain.com",
                expected_subject="Correct Subject",
                expected_body="Original expected body."
            ))

            self.assertIsNone(reconciled)

    # --------------------------------------------------------------------------
    # 9. Reconcile Gmail draft returns None safely on network error
    # --------------------------------------------------------------------------
    def test_09_reconcile_gmail_draft_network_error_safety(self):
        """Verifies that reconcile_gmail_draft handles network exceptions safely without crashing or leaking tokens."""
        mock_http_get = AsyncMock(side_effect=Exception(f"Connection timed out with token {self.mock_token}"))

        with patch("backend.google_service.get_valid_access_token", new=AsyncMock(return_value=self.mock_token)), \
             patch.object(gs, "HAS_WORKER_FETCH", True), \
             patch("backend.google_service.http_get", new=mock_http_get):

            reconciled = asyncio.run(reconcile_gmail_draft(
                user_id=self.mock_user_id,
                approval_id="appr_net_err_01",
                expected_to="target@domain.com",
                expected_subject="Subj",
                expected_body="Body"
            ))

            self.assertIsNone(reconciled)

    # --------------------------------------------------------------------------
    # 10. Positional argument backward-compatibility for _client_post
    # --------------------------------------------------------------------------
    def test_10_client_post_positional_argument_order_preserved(self):
        """Verifies _client_post strictly preserves original positional order: (url, data, headers, timeout)."""
        from backend.google_service import _client_post

        # Test A: Worker runtime with all 4 positional parameters
        mock_http_post = AsyncMock(return_value=WorkerHttpResponse(200, '{"ok": true}', {"ok": True}))
        with patch.object(gs, "HAS_WORKER_FETCH", True), \
             patch("backend.google_service.http_post", new=mock_http_post):

            res = asyncio.run(_client_post(
                "https://oauth2.googleapis.com/token",
                {"client_id": "test_cid", "code": "auth_code_123"},
                {"Content-Type": "application/x-www-form-urlencoded"},
                25.0
            ))

            self.assertEqual(res.status_code, 200)
            mock_http_post.assert_awaited_once_with(
                "https://oauth2.googleapis.com/token",
                data={"client_id": "test_cid", "code": "auth_code_123"},
                json_data=None,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=25.0
            )

        # Test B: Local runtime with all 4 positional parameters
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        client_inst = AsyncMock()
        client_inst.post.return_value = mock_resp
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=client_inst)
        cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(gs, "HAS_WORKER_FETCH", False), \
             patch("backend.google_service.httpx.AsyncClient", return_value=cm) as mock_cls:

            res = asyncio.run(_client_post(
                "https://oauth2.googleapis.com/token",
                {"client_id": "test_cid"},
                {"Authorization": "Basic dGVzdA=="},
                18.0
            ))

            self.assertEqual(res.status_code, 200)
            mock_cls.assert_called_once_with(timeout=18.0)
            client_inst.post.assert_awaited_once_with(
                "https://oauth2.googleapis.com/token",
                data={"client_id": "test_cid"},
                json=None,
                headers={"Authorization": "Basic dGVzdA=="},
                timeout=18.0
            )

    # --------------------------------------------------------------------------
    # 11. Keyword argument compatibility (json_data and json alias)
    # --------------------------------------------------------------------------
    def test_11_client_post_keyword_json_data_and_alias_support(self):
        """Verifies _client_post supports json_data keyword and json alias without positional argument collision."""
        from backend.google_service import _client_post

        # Test json_data=... keyword in Worker mode
        mock_http_post = AsyncMock(return_value=WorkerHttpResponse(200, '{"id": "d1"}', {"id": "d1"}))
        with patch.object(gs, "HAS_WORKER_FETCH", True), \
             patch("backend.google_service.http_post", new=mock_http_post):

            asyncio.run(_client_post(
                "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
                headers={"Authorization": "Bearer tok"},
                json_data={"message": {"raw": "abc"}},
                timeout=10.0
            ))

            mock_http_post.assert_awaited_once_with(
                "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
                data=None,
                json_data={"message": {"raw": "abc"}},
                headers={"Authorization": "Bearer tok"},
                timeout=10.0
            )

        # Test json=... alias in Worker mode
        mock_http_post.reset_mock()
        with patch.object(gs, "HAS_WORKER_FETCH", True), \
             patch("backend.google_service.http_post", new=mock_http_post):

            asyncio.run(_client_post(
                "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
                headers={"Authorization": "Bearer tok"},
                json={"message": {"raw": "xyz"}},
                timeout=12.0
            ))

            mock_http_post.assert_awaited_once_with(
                "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
                data=None,
                json_data={"message": {"raw": "xyz"}},
                headers={"Authorization": "Bearer tok"},
                timeout=12.0
            )

    # --------------------------------------------------------------------------
    # 12. Partial positional arguments with default values
    # --------------------------------------------------------------------------
    def test_12_client_post_partial_positional_defaults(self):
        """Verifies _client_post correctly handles calls with only 1 or 2 positional arguments using standard defaults."""
        from backend.google_service import _client_post

        mock_http_post = AsyncMock(return_value=WorkerHttpResponse(200, '{}', {}))
        with patch.object(gs, "HAS_WORKER_FETCH", True), \
             patch("backend.google_service.http_post", new=mock_http_post):

            asyncio.run(_client_post("https://api.example.com/status"))

            mock_http_post.assert_awaited_once_with(
                "https://api.example.com/status",
                data=None,
                json_data=None,
                headers=None,
                timeout=15.0
            )


if __name__ == "__main__":
    unittest.main()
