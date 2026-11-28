"""
Targeted regression tests for Stage 1 Production Safeguards:
1. Encryption key resolution, fail-closed behavior, and Fernet cache concurrency.
2. Cloudflare D1 database adapter fail-closed behavior in production and worker runtimes.
"""

import os
import unittest
import concurrent.futures
from unittest.mock import patch, MagicMock
from cryptography.fernet import Fernet

from backend.security import (
    get_encryption_key,
    get_fernet,
    get_fernet_for_key,
    encrypt_token,
    decrypt_token,
    DEV_FALLBACK_KEY,
    is_worker_context as is_security_worker_context,
    is_production as is_security_production,
)
from backend.database import (
    CloudflareD1DatabaseAdapter,
    get_db,
    _is_worker_context as is_db_worker_context,
    _is_production_environment,
)


class MockWorkerEnvWithKey:
    def __init__(self, key: str, environment: str = None):
        self.ENCRYPTION_KEY = key
        if environment is not None:
            self.ENVIRONMENT = environment


class MockWorkerEnvNoKey:
    def __init__(self, environment: str = None):
        if environment is not None:
            self.ENVIRONMENT = environment


class MockWorkerEnvWithD1:
    def __init__(self, environment: str = None):
        if environment is not None:
            self.ENVIRONMENT = environment
        self.DB = MagicMock()
        mock_stmt = MagicMock()
        mock_stmt.bind.return_value = mock_stmt
        mock_stmt.all.return_value = {"results": [{"test_col": "val"}], "success": True, "meta": {}}
        self.DB.prepare.return_value = mock_stmt


class MockWorkerEnvNoD1:
    def __init__(self, environment: str = None):
        if environment is not None:
            self.ENVIRONMENT = environment


class TestEncryptionProductionSafeguards(unittest.TestCase):
    """Regression tests for encryption key handling and worker fail-closed logic."""

    def setUp(self):
        self.valid_key = Fernet.generate_key().decode()
        self.valid_key_2 = Fernet.generate_key().decode()

    def test_production_missing_key_raises_runtime_error(self):
        """In production environment without ENCRYPTION_KEY, get_encryption_key must raise RuntimeError."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
            if "ENCRYPTION_KEY" in os.environ:
                del os.environ["ENCRYPTION_KEY"]
            with self.assertRaises(RuntimeError) as ctx:
                get_encryption_key()
            self.assertIn("ENCRYPTION_KEY is required", str(ctx.exception))

    def test_production_missing_key_via_worker_env_raises_runtime_error(self):
        """In production worker env without ENCRYPTION_KEY, get_encryption_key must raise RuntimeError."""
        env = MockWorkerEnvNoKey(environment="production")
        with patch.dict(os.environ, {}, clear=False):
            if "ENCRYPTION_KEY" in os.environ:
                del os.environ["ENCRYPTION_KEY"]
            with self.assertRaises(RuntimeError) as ctx:
                get_encryption_key(worker_env=env)
            self.assertIn("ENCRYPTION_KEY is required", str(ctx.exception))

    def test_production_invalid_key_raises_runtime_error(self):
        """In production environment with invalid ENCRYPTION_KEY, get_encryption_key must raise RuntimeError."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "ENCRYPTION_KEY": "invalid-fernet-key-value"}):
            with self.assertRaises(RuntimeError) as ctx:
                get_encryption_key()
            self.assertIn("Invalid ENCRYPTION_KEY configured", str(ctx.exception))

    def test_production_valid_configured_key_works(self):
        """In production environment with valid ENCRYPTION_KEY, key resolves and encrypt/decrypt works."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "ENCRYPTION_KEY": self.valid_key}):
            resolved = get_encryption_key()
            self.assertEqual(resolved, self.valid_key)

            token_sample = "ya29.sample_oauth_token_production"
            encrypted = encrypt_token(token_sample)
            self.assertNotEqual(encrypted, token_sample)
            decrypted = decrypt_token(encrypted)
            self.assertEqual(decrypted, token_sample)

    def test_production_valid_configured_key_via_worker_env_works(self):
        """In production worker env with valid ENCRYPTION_KEY, key resolves correctly."""
        env = MockWorkerEnvWithKey(key=self.valid_key, environment="production")
        resolved = get_encryption_key(worker_env=env)
        self.assertEqual(resolved, self.valid_key)

    def test_test_mode_and_dev_fallback_remains_functional(self):
        """In non-worker, development environment without key, fallback key is preserved."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            if "ENCRYPTION_KEY" in os.environ:
                del os.environ["ENCRYPTION_KEY"]
            if "WORKER_ENV" in os.environ:
                del os.environ["WORKER_ENV"]
            if "CF_PAGES" in os.environ:
                del os.environ["CF_PAGES"]
            resolved = get_encryption_key()
            self.assertEqual(resolved, DEV_FALLBACK_KEY)

    def test_existing_encrypted_data_decryptable_with_configured_key(self):
        """Data encrypted with a specific valid key remains decryptable using that key."""
        custom_fernet = Fernet(self.valid_key.encode())
        plain_secret = "gmail_refresh_token_xyz_987"
        encrypted_data = custom_fernet.encrypt(plain_secret.encode()).decode()

        with patch.dict(os.environ, {"ENVIRONMENT": "production", "ENCRYPTION_KEY": self.valid_key}):
            recovered = decrypt_token(encrypted_data)
            self.assertEqual(recovered, plain_secret)

    # -------------------------------------------------------------
    # SPECIFIC STAGE 1 CORRECTION TESTS (A, D, H, I)
    # -------------------------------------------------------------
    def test_A_worker_context_missing_environment_and_key_raises_runtime_error(self):
        """Requirement A: Worker context with missing ENVIRONMENT and missing ENCRYPTION_KEY must raise RuntimeError."""
        env = MockWorkerEnvNoKey(environment=None)  # No ENVIRONMENT attribute
        with patch.dict(os.environ, {"ENVIRONMENT": ""}, clear=False):
            if "ENCRYPTION_KEY" in os.environ:
                del os.environ["ENCRYPTION_KEY"]
            with self.assertRaises(RuntimeError) as ctx:
                get_encryption_key(worker_env=env)
            self.assertIn("ENCRYPTION_KEY is required in Cloudflare Worker", str(ctx.exception))

    def test_D_worker_context_with_valid_encryption_key_works(self):
        """Requirement D: Worker context with valid encryption key must work cleanly."""
        env = MockWorkerEnvWithKey(key=self.valid_key, environment=None)
        with patch.dict(os.environ, {"ENVIRONMENT": ""}, clear=False):
            resolved = get_encryption_key(worker_env=env)
            self.assertEqual(resolved, self.valid_key)

            encrypted = encrypt_token("worker_secret_payload", worker_env=env)
            decrypted = decrypt_token(encrypted, worker_env=env)
            self.assertEqual(decrypted, "worker_secret_payload")

    def test_H_fernet_key_context_switching_and_concurrency(self):
        """Requirement H: Fernet key cache safely handles context switching and concurrent callers."""
        # Key 1 and Key 2 encrypt distinct payloads
        key_1 = self.valid_key
        key_2 = self.valid_key_2

        fernet_1 = get_fernet_for_key(key_1)
        fernet_2 = get_fernet_for_key(key_2)
        self.assertIsNot(fernet_1, fernet_2)

        def worker_task(key, payload):
            f = get_fernet_for_key(key)
            enc = f.encrypt(payload.encode()).decode()
            dec = f.decrypt(enc.encode()).decode()
            return dec == payload

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = []
            for i in range(40):
                k = key_1 if i % 2 == 0 else key_2
                p = f"payload_{i}_{k[:8]}"
                futures.append(executor.submit(worker_task, k, p))
            for fut in concurrent.futures.as_completed(futures):
                self.assertTrue(fut.result())

    def test_I_worker_env_and_cf_pages_encryption_detection_without_environment(self):
        """Requirement I: WORKER_ENV=1 and CF_PAGES=1 trigger fail-closed encryption without ENVIRONMENT=production."""
        with patch.dict(os.environ, {"WORKER_ENV": "1", "ENVIRONMENT": "development"}, clear=False):
            if "ENCRYPTION_KEY" in os.environ:
                del os.environ["ENCRYPTION_KEY"]
            with self.assertRaises(RuntimeError) as ctx:
                get_encryption_key()
            self.assertIn("ENCRYPTION_KEY is required", str(ctx.exception))

        with patch.dict(os.environ, {"CF_PAGES": "1", "ENVIRONMENT": "development"}, clear=False):
            if "ENCRYPTION_KEY" in os.environ:
                del os.environ["ENCRYPTION_KEY"]
            with self.assertRaises(RuntimeError) as ctx:
                get_encryption_key()
            self.assertIn("ENCRYPTION_KEY is required", str(ctx.exception))


class TestDatabaseProductionSafeguards(unittest.TestCase):
    """Regression tests for D1 database adapter safeguards and worker detection."""

    def test_production_missing_d1_binding_and_credentials_raises_runtime_error(self):
        """In production, missing D1 binding and credentials must raise RuntimeError."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
            for k in ["CF_ACCOUNT_ID", "CF_D1_DATABASE_ID", "CF_API_TOKEN"]:
                os.environ.pop(k, None)

            with self.assertRaises(RuntimeError) as ctx:
                CloudflareD1DatabaseAdapter(test_mode=False)
            self.assertIn("Cloudflare D1 requires an active worker environment", str(ctx.exception))

    def test_production_worker_env_missing_d1_binding_raises_runtime_error(self):
        """In production with a worker env that lacks DB binding, adapter raises RuntimeError."""
        env = MockWorkerEnvNoD1(environment="production")
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
            for k in ["CF_ACCOUNT_ID", "CF_D1_DATABASE_ID", "CF_API_TOKEN"]:
                os.environ.pop(k, None)

            with self.assertRaises(RuntimeError) as ctx:
                CloudflareD1DatabaseAdapter(worker_env=env)
            self.assertIn("Cloudflare D1 requires an active worker environment", str(ctx.exception))

    def test_test_mode_supports_in_memory_sqlite_in_non_production_non_worker(self):
        """Explicit test_mode=True in development/test allows in-memory SQLite initialization only outside worker context."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            for k in ["WORKER_ENV", "CF_PAGES"]:
                os.environ.pop(k, None)
            adapter = CloudflareD1DatabaseAdapter(test_mode=True)
            self.assertIsNotNone(adapter._test_conn)

            res = adapter.execute("SELECT 1 AS num")
            row = res.fetchone()
            self.assertEqual(row["num"], 1)

    def test_production_test_mode_cannot_bypass_safeguard(self):
        """In production, test_mode=True must not silently open in-memory SQLite when credentials missing."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
            for k in ["CF_ACCOUNT_ID", "CF_D1_DATABASE_ID", "CF_API_TOKEN"]:
                os.environ.pop(k, None)

            with self.assertRaises(RuntimeError) as ctx:
                CloudflareD1DatabaseAdapter(test_mode=True)
            self.assertIn("Cloudflare D1 requires an active worker environment", str(ctx.exception))

    def test_existing_valid_d1_worker_binding_unchanged(self):
        """Valid D1 worker environment binding initializes without error in production."""
        env = MockWorkerEnvWithD1(environment="production")
        adapter = CloudflareD1DatabaseAdapter(worker_env=env)
        self.assertIsNone(adapter._test_conn)
        self.assertEqual(adapter.worker_env, env)

        res = adapter.execute("SELECT * FROM test")
        row = res.fetchone()
        self.assertEqual(row["test_col"], "val")

    def test_existing_valid_d1_rest_credentials_unchanged(self):
        """Valid D1 REST API credentials initialize without error in production."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
            adapter = CloudflareD1DatabaseAdapter(
                account_id="mock_acc_123",
                database_id="mock_db_456",
                api_token="mock_tok_789",
                test_mode=False
            )
            self.assertIsNone(adapter._test_conn)
            self.assertEqual(adapter.account_id, "mock_acc_123")
            self.assertEqual(adapter.database_id, "mock_db_456")

    def test_existing_local_development_configuration_remains_functional(self):
        """get_db() with default sqlite adapter continues to return a valid local SQLite connection."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            for k in ["WORKER_ENV", "CF_PAGES"]:
                os.environ.pop(k, None)
            conn = get_db(adapter="sqlite")
            self.assertIsNotNone(conn)
            cur = conn.cursor()
            cur.execute("SELECT 1 AS val")
            row = cur.fetchone()
            self.assertEqual(row["val"], 1)

    # -------------------------------------------------------------
    # SPECIFIC STAGE 1 CORRECTION TESTS (B, C, E, F, G, I)
    # -------------------------------------------------------------
    def test_B_worker_context_missing_environment_and_db_raises_runtime_error(self):
        """Requirement B: Worker context with missing ENVIRONMENT and missing DB/REST credentials must raise RuntimeError."""
        env = MockWorkerEnvNoD1(environment=None)  # Worker context without ENVIRONMENT
        with patch.dict(os.environ, {"ENVIRONMENT": ""}, clear=False):
            for k in ["CF_ACCOUNT_ID", "CF_D1_DATABASE_ID", "CF_API_TOKEN"]:
                os.environ.pop(k, None)

            with self.assertRaises(RuntimeError) as ctx:
                CloudflareD1DatabaseAdapter(worker_env=env)
            self.assertIn("Cloudflare D1 requires an active worker environment", str(ctx.exception))

    def test_C_worker_context_cannot_be_bypassed_by_test_overrides(self):
        """Requirement C: Worker context must fail closed even when test flags are set individually."""
        env = MockWorkerEnvNoD1(environment=None)

        test_override_scenarios = [
            {"CF_D1_TEST_MODE": "1"},
            {"DEV_TEST_MODE": "true"},
            {"TESTING": "1"},
            {"PYTEST_CURRENT_TEST": "test_case"},
        ]

        for override in test_override_scenarios:
            with patch.dict(os.environ, {**override, "ENVIRONMENT": ""}, clear=False):
                for k in ["CF_ACCOUNT_ID", "CF_D1_DATABASE_ID", "CF_API_TOKEN"]:
                    os.environ.pop(k, None)

                with self.assertRaises(RuntimeError, msg=f"Failed to fail closed under override {override}") as ctx:
                    CloudflareD1DatabaseAdapter(worker_env=env)
                self.assertIn("Cloudflare D1 requires an active worker environment", str(ctx.exception))

        # Test explicit test_mode=True parameter inside worker context
        with patch.dict(os.environ, {"ENVIRONMENT": ""}, clear=False):
            for k in ["CF_ACCOUNT_ID", "CF_D1_DATABASE_ID", "CF_API_TOKEN"]:
                os.environ.pop(k, None)
            with self.assertRaises(RuntimeError, msg="Failed to fail closed under test_mode=True") as ctx:
                CloudflareD1DatabaseAdapter(worker_env=env, test_mode=True)
            self.assertIn("Cloudflare D1 requires an active worker environment", str(ctx.exception))

    def test_E_worker_context_with_valid_d1_binding_works(self):
        """Requirement E: Worker context with a valid D1 binding must work cleanly."""
        env = MockWorkerEnvWithD1(environment=None)
        adapter = CloudflareD1DatabaseAdapter(worker_env=env)
        self.assertIsNone(adapter._test_conn)

        res = adapter.execute("SELECT * FROM test")
        row = res.fetchone()
        self.assertEqual(row["test_col"], "val")

    def test_F_worker_context_with_valid_rest_credentials_retains_rest_mode(self):
        """Requirement F: Worker context with valid REST credentials must retain supported REST mode."""
        env = MockWorkerEnvNoD1(environment=None)
        adapter = CloudflareD1DatabaseAdapter(
            worker_env=env,
            account_id="cf_acc_999",
            database_id="cf_db_888",
            api_token="cf_tok_777",
        )
        self.assertIsNone(adapter._test_conn)
        self.assertEqual(adapter.account_id, "cf_acc_999")
        self.assertEqual(adapter.database_id, "cf_db_888")
        self.assertEqual(adapter.api_token, "cf_tok_777")

    def test_G_local_development_and_explicit_non_production_test_mode(self):
        """Requirement G: Local development and explicit non-production test mode must still work."""
        # 1. Non-worker explicit test mode creates in-memory SQLite
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            for k in ["WORKER_ENV", "CF_PAGES"]:
                os.environ.pop(k, None)
            adapter = CloudflareD1DatabaseAdapter(test_mode=True)
            self.assertIsNotNone(adapter._test_conn)
            res = adapter.execute("SELECT 'test_mode' AS mode")
            self.assertEqual(res.fetchone()["mode"], "test_mode")

        # 2. Local development SQLite adapter
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            for k in ["WORKER_ENV", "CF_PAGES"]:
                os.environ.pop(k, None)
            conn = get_db(adapter="sqlite")
            self.assertIsNotNone(conn)
            cur = conn.cursor()
            cur.execute("SELECT 'dev_mode' AS mode")
            self.assertEqual(cur.fetchone()["mode"], "dev_mode")

    def test_I_worker_env_and_cf_pages_database_detection_without_environment(self):
        """Requirement I: WORKER_ENV=1 and CF_PAGES=1 trigger fail-closed database guard without ENVIRONMENT=production."""
        with patch.dict(os.environ, {"WORKER_ENV": "1", "ENVIRONMENT": "development"}, clear=False):
            for k in ["CF_ACCOUNT_ID", "CF_D1_DATABASE_ID", "CF_API_TOKEN"]:
                os.environ.pop(k, None)
            with self.assertRaises(RuntimeError) as ctx:
                CloudflareD1DatabaseAdapter()
            self.assertIn("Cloudflare D1 requires an active worker environment", str(ctx.exception))

        with patch.dict(os.environ, {"CF_PAGES": "1", "ENVIRONMENT": "development"}, clear=False):
            for k in ["CF_ACCOUNT_ID", "CF_D1_DATABASE_ID", "CF_API_TOKEN"]:
                os.environ.pop(k, None)
            with self.assertRaises(RuntimeError) as ctx:
                CloudflareD1DatabaseAdapter()
            self.assertIn("Cloudflare D1 requires an active worker environment", str(ctx.exception))
