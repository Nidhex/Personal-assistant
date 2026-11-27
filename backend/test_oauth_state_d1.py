"""
Phase 4 Regression Tests: OAuth State Lifecycle, D1 Async Promise Resolution,
Expiration Validation, Replay Prevention, and Multi-user Isolation.
"""
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from backend.database import (
    D1QueryResult,
    D1Cursor,
    CloudflareD1DatabaseAdapter,
    SQLiteConnectionWrapper,
    SQLiteCursorWrapper,
    get_db,
    init_db
)
from backend.security import (
    generate_oauth_state,
    is_expired,
    generate_session_id,
    get_session_expiry
)
from backend.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_oauth_state_generation_and_expiry_format():
    """Verify state token entropy, length, and timestamp serialization."""
    state = generate_oauth_state()
    assert isinstance(state, str)
    assert len(state) >= 24

    # Timestamp 15 minutes in future
    now = datetime.now(timezone.utc)
    future = (now + timedelta(minutes=15)).isoformat()
    assert not is_expired(future)

    # Past timestamp must be expired
    past = (now - timedelta(seconds=1)).isoformat()
    assert is_expired(past)

    # Zulu timestamp format
    past_zulu = "2020-01-01T00:00:00Z"
    assert is_expired(past_zulu)


@pytest.mark.asyncio
async def test_d1_async_promise_unwrapping():
    """
    Simulates Cloudflare Python Worker Pyodide runtime where stmt.all()
    returns an awaitable Promise whose resolution produces a JsProxy/dict with .results.
    """
    class MockJsResult:
        def __init__(self, data):
            self._data = data

        def to_py(self):
            return self._data

    class MockD1Statement:
        def __init__(self, sql, params=None):
            self.sql = sql
            self.params = params or []

        def bind(self, *p):
            self.params = list(p)
            return self

        async def all(self):
            # Simulates async execution against D1
            await asyncio.sleep(0.01)
            return MockJsResult({
                "results": [
                    {"state": self.params[0] if self.params else "test_state",
                     "action": "login",
                     "user_id": "usr_test",
                     "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}
                ],
                "meta": {"changes": 0, "last_row_id": None},
                "success": True
            })

    class MockWorkerDB:
        def prepare(self, sql):
            return MockD1Statement(sql)

    class MockWorkerEnv:
        def __init__(self):
            self.DB = MockWorkerDB()

    adapter = CloudflareD1DatabaseAdapter(worker_env=MockWorkerEnv())
    cursor = adapter.cursor()

    # Await cursor.execute (the Cloudflare Worker pattern)
    await cursor.execute("SELECT state, action, user_id, expires_at FROM oauth_states WHERE state = ?", ("test_state_123",))
    row = cursor.fetchone()

    assert row is not None
    assert row["state"] == "test_state_123"
    assert row["action"] == "login"
    assert not is_expired(row["expires_at"])


@pytest.mark.asyncio
async def test_sqlite_wrapper_dual_compat():
    """
    Verifies that SQLiteConnectionWrapper supports both:
    1. Synchronous cursor.execute(...) / conn.execute(...)
    2. Asynchronous await cursor.execute(...) / await conn.execute(...)
    """
    conn = get_db(adapter="sqlite")
    init_db(conn)

    # 1. Async execution
    state_async = "async_state_" + generate_oauth_state()
    exp_async = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    await conn.execute(
        "INSERT INTO oauth_states (state, action, user_id, expires_at) VALUES (?, ?, ?, ?)",
        (state_async, "login", None, exp_async)
    )

    cur = conn.cursor()
    await cur.execute("SELECT state, expires_at FROM oauth_states WHERE state = ?", (state_async,))
    row = cur.fetchone()
    assert row is not None
    assert row["state"] == state_async

    # 2. Sync execution (backward compatibility for legacy tests)
    state_sync = "sync_state_" + generate_oauth_state()
    exp_sync = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    conn.execute(
        "INSERT INTO oauth_states (state, action, user_id, expires_at) VALUES (?, ?, ?, ?)",
        (state_sync, "login", None, exp_sync)
    )

    cur2 = conn.cursor()
    cur2.execute("SELECT state, expires_at FROM oauth_states WHERE state = ?", (state_sync,))
    row2 = cur2.fetchone()
    assert row2 is not None
    assert row2["state"] == state_sync

    # Cleanup
    conn.execute("DELETE FROM oauth_states WHERE state IN (?, ?)", (state_async, state_sync))
    conn.close()


def test_oauth_url_endpoint_generates_and_stores_state():
    """Verify /api/auth/google/url inserts state in D1/SQLite with 15-minute expiry."""
    with patch("backend.main.is_google_configured", return_value=True):
        resp = client.get("/api/auth/google/url")
        assert resp.status_code == 200
        data = resp.json()
        assert "auth_url" in data
        assert "state=" in data["auth_url"]

        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(data["auth_url"])
        qs = parse_qs(parsed.query)
        extracted_state = qs["state"][0]

        # Verify state is present in the database
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT state, expires_at FROM oauth_states WHERE state = ?", (extracted_state,))
        row = cur.fetchone()
        assert row is not None
        assert row["state"] == extracted_state
        assert not is_expired(row["expires_at"])

        # Clean up
        conn.execute("DELETE FROM oauth_states WHERE state = ?", (extracted_state,))
        conn.close()


def test_oauth_callback_expired_state_rejection():
    """Verify expired state (> 15 minutes) is rejected with invalid_or_expired_state."""
    expired_state = "expired_" + generate_oauth_state()
    past_ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

    conn = get_db()
    conn.execute(
        "INSERT INTO oauth_states (state, action, user_id, expires_at) VALUES (?, ?, ?, ?)",
        (expired_state, "login", None, past_ts)
    )
    conn.commit()
    conn.close()

    resp = client.get(f"/api/auth/google/callback?code=fake_code&state={expired_state}", follow_redirects=False)
    assert resp.status_code == 307
    location = resp.headers.get("location", "")
    assert "auth_error=invalid_or_expired_state" in location

    # Clean up
    conn = get_db()
    conn.execute("DELETE FROM oauth_states WHERE state = ?", (expired_state,))
    conn.commit()
    conn.close()


def test_oauth_callback_replay_prevention():
    """Verify once a state is consumed or rejected, replay attempt fails."""
    valid_state = "valid_" + generate_oauth_state()
    future_ts = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()

    conn = get_db()
    conn.execute(
        "INSERT INTO oauth_states (state, action, user_id, expires_at) VALUES (?, ?, ?, ?)",
        (valid_state, "login", None, future_ts)
    )
    conn.commit()
    conn.close()

    # First attempt: state exists, code exchange fails or succeeds
    with patch("backend.main.exchange_code_for_tokens", side_effect=Exception("mock_token_fail")):
        resp1 = client.get(f"/api/auth/google/callback?code=code1&state={valid_state}", follow_redirects=False)
        assert resp1.status_code == 307
        loc1 = resp1.headers.get("location", "")
        # Because exchange_code_for_tokens was called, state was already validated and deleted!
        assert "mock_token_fail" in loc1

    # Second attempt with same state (Replay attack): state was deleted from D1/database
    resp2 = client.get(f"/api/auth/google/callback?code=code2&state={valid_state}", follow_redirects=False)
    assert resp2.status_code == 307
    loc2 = resp2.headers.get("location", "")
    assert "auth_error=invalid_or_expired_state" in loc2


def test_oauth_state_multi_user_isolation():
    """Verify multiple concurrent OAuth state generations do not overwrite or interfere."""
    state_user_a = "user_a_" + generate_oauth_state()
    state_user_b = "user_b_" + generate_oauth_state()
    exp = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()

    conn = get_db()
    conn.execute(
        "INSERT INTO oauth_states (state, action, user_id, expires_at) VALUES (?, ?, ?, ?)",
        (state_user_a, "login", "usr_a", exp)
    )
    conn.execute(
        "INSERT INTO oauth_states (state, action, user_id, expires_at) VALUES (?, ?, ?, ?)",
        (state_user_b, "login", "usr_b", exp)
    )

    cur = conn.cursor()
    cur.execute("SELECT state FROM oauth_states WHERE state IN (?, ?)", (state_user_a, state_user_b))
    states = [r["state"] for r in cur.fetchall()]
    assert len(states) == 2
    assert state_user_a in states
    assert state_user_b in states

    # Deleting user A's state leaves user B untouched
    conn.execute("DELETE FROM oauth_states WHERE state = ?", (state_user_a,))
    cur.execute("SELECT state FROM oauth_states WHERE state = ?", (state_user_b,))
    row_b = cur.fetchone()
    assert row_b is not None
    assert row_b["state"] == state_user_b

    # Cleanup
    conn.execute("DELETE FROM oauth_states WHERE state = ?", (state_user_b,))
    conn.close()
