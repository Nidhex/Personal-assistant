import unittest
import os
import asyncio
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from backend.main import app, current_worker_env
from backend.worker import default, handle_worker_scheduled_tick
from backend.database import get_db, CloudflareD1DatabaseAdapter
from backend.security import get_encryption_key, encrypt_token, decrypt_token
from backend.google_service import is_google_configured, get_config_val

class MockD1PreparedStatement:
    def __init__(self, sql):
        self.sql = sql
        self.params = []

    def bind(self, *params):
        self.params = list(params)
        return self

    def all(self):
        return {"results": [{"mock_col": "worker_val"}], "success": True, "meta": {}}

    def first(self, col=None):
        return "worker_val" if col == "mock_col" else {"mock_col": "worker_val"}

    def run(self):
        return {"success": True, "meta": {"changes": 1}}

class MockD1Database:
    def prepare(self, sql):
        return MockD1PreparedStatement(sql)

class MockWorkerEnvironment:
    def __init__(self):
        self.DB = MockD1Database()
        self.ENCRYPTION_KEY = "iQnigQRzfYgqAbCPd9-w6JJ0U5pM1Uvv2a13DetxoM8="
        self.GOOGLE_CLIENT_ID = "mock-worker-client-id.apps.googleusercontent.com"
        self.GOOGLE_CLIENT_SECRET = "mock-worker-client-secret"
        self.GEMINI_API_KEY = "mock-worker-gemini-key"

class TestCloudflareWorkerCompatibility(unittest.TestCase):
    def test_01_pyodide_dependencies_audit(self):
        """Verifies that all required packages for Cloudflare Python Worker are importable."""
        import fastapi
        import pydantic
        import httpx
        import cryptography
        import dotenv

        self.assertIsNotNone(fastapi.__version__)
        self.assertIsNotNone(pydantic.__version__)
        self.assertIsNotNone(httpx.__version__)
        self.assertIsNotNone(cryptography.__version__)

    def test_02_asgi_entrypoint_exists(self):
        """Verifies that the Worker entrypoint exports a valid ASGI default application."""
        self.assertIsNotNone(default)
        self.assertTrue(callable(default) or hasattr(default, "fetch"))

    def test_03_worker_env_middleware_and_secret_resolution(self):
        """Verifies that scope['env'] bindings are captured and resolve secrets dynamically."""
        mock_env = MockWorkerEnvironment()
        client = TestClient(app)

        # Before request with worker env: ContextVar should be None
        self.assertIsNone(current_worker_env.get())

        # Test health/status endpoint with custom worker scope injection
        # We manually test the contextvar behavior that the middleware runs
        token = current_worker_env.set(mock_env)
        try:
            # 1. Encryption key resolution from env
            resolved_key = get_encryption_key()
            self.assertEqual(resolved_key, mock_env.ENCRYPTION_KEY)

            # 2. Google OAuth client ID resolution from env
            resolved_cid = get_config_val("GOOGLE_CLIENT_ID")
            self.assertEqual(resolved_cid, mock_env.GOOGLE_CLIENT_ID)
            self.assertTrue(is_google_configured())

            # 3. Automatic D1 Adapter resolution when env.DB is present
            db = get_db()
            self.assertIsInstance(db, CloudflareD1DatabaseAdapter)
            self.assertEqual(db.worker_env, mock_env)

            # 4. Test query through worker D1 binding
            res = db.execute("SELECT * FROM test")
            row = res.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row.get("mock_col"), "worker_val")
        finally:
            current_worker_env.reset(token)

        # After request: ContextVar is reset back to None
        self.assertIsNone(current_worker_env.get())

    def test_04_fernet_encryption_in_worker_environment(self):
        """Verifies that token encryption and decryption work under Worker env key."""
        mock_env = MockWorkerEnvironment()
        token = current_worker_env.set(mock_env)
        try:
            test_token = "ya29.a0AfH6SMD_SECRET_GMAIL_TOKEN_12345"
            encrypted = encrypt_token(test_token)
            self.assertNotEqual(encrypted, test_token)
            self.assertTrue(len(encrypted) > 20)

            decrypted = decrypt_token(encrypted)
            self.assertEqual(decrypted, test_token)
        finally:
            current_worker_env.reset(token)

    def test_05_outbound_httpx_async_client(self):
        """Verifies that httpx async client executes cleanly for outbound API integrations."""
        async def mock_fetch():
            import httpx
            # Use mock transport to verify async client flow without live network dependencies
            transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"status": "ok"}))
            async with httpx.AsyncClient(transport=transport) as client:
                resp = await client.get("https://generativelanguage.googleapis.com/v1beta/models")
                return resp.json()

        result = asyncio.run(mock_fetch())
        self.assertEqual(result, {"status": "ok"})

    def test_06_worker_scheduled_cron_handler(self):
        """Verifies handle_worker_scheduled_tick executes cleanly for Cloudflare Cron Triggers."""
        mock_env = MockWorkerEnvironment()
        # Mock database call during tick to avoid dependencies on existing database state
        with patch("backend.scheduler.get_db") as mock_get_db:
            mock_conn = MagicMock()
            mock_cur = MagicMock()
            mock_cur.fetchall.return_value = []
            mock_conn.cursor.return_value = mock_cur
            mock_get_db.return_value = mock_conn

            tick_result = asyncio.run(handle_worker_scheduled_tick(mock_env))
            self.assertTrue(tick_result["success"])
            self.assertEqual(tick_result["runs_triggered"], 0)

    def test_07_local_sqlite_fallback_preserved(self):
        """Verifies that outside of Worker environment, standard SQLite is returned."""
        # Ensure contextvar is None
        self.assertIsNone(current_worker_env.get())
        conn = get_db()
        # Standard sqlite3 connection
        import sqlite3
        self.assertIsInstance(conn, sqlite3.Connection)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        self.assertEqual(cur.fetchone()[0], 1)
        conn.close()

if __name__ == "__main__":
    unittest.main()
