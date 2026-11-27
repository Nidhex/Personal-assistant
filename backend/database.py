import sqlite3
import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

DB_PATH = Path(__file__).parent / "data.db"
DEFAULT_ADAPTER = os.getenv("DB_ADAPTER", "sqlite").lower()

class D1QueryResult:
    """
    Standard query result wrapping Cloudflare D1 query results.
    Provides fetchone(), fetchall(), rowcount, lastrowid, and dict/attribute access.
    """
    def __init__(self, results: List[Dict[str, Any]], meta: Optional[Dict[str, Any]] = None, success: bool = True):
        self._results = results or []
        self._meta = meta or {}
        self.success = success
        self._cursor_idx = 0

    @property
    def rowcount(self) -> int:
        return self._meta.get("changes", len(self._results))

    @property
    def lastrowid(self) -> Optional[int]:
        return self._meta.get("last_row_id")

    def fetchone(self) -> Optional[Dict[str, Any]]:
        if self._cursor_idx < len(self._results):
            row = self._results[self._cursor_idx]
            self._cursor_idx += 1
            return row
        return None

    def fetchall(self) -> List[Dict[str, Any]]:
        remaining = self._results[self._cursor_idx:]
        self._cursor_idx = len(self._results)
        return remaining

    def __iter__(self):
        return iter(self._results)

    def __len__(self):
        return len(self._results)


class D1PreparedStatement:
    """
    Implements the official Cloudflare D1 prepared statement interface:
    stmt = db.prepare(sql).bind(*params)
    results = stmt.all() / stmt.first() / stmt.run() / stmt.raw()
    """
    def __init__(self, adapter: "CloudflareD1DatabaseAdapter", sql: str):
        self.adapter = adapter
        self.sql = sql
        self.params: List[Any] = []

    def bind(self, *params) -> "D1PreparedStatement":
        self.params = list(params)
        return self

    def all(self) -> Dict[str, Any]:
        res = self.adapter.execute(self.sql, self.params)
        return {
            "results": res.fetchall(),
            "success": res.success,
            "meta": res._meta
        }

    def first(self, col_name: Optional[str] = None) -> Any:
        res = self.adapter.execute(self.sql, self.params)
        row = res.fetchone()
        if not row:
            return None
        if col_name:
            return row.get(col_name)
        return row

    def run(self) -> Dict[str, Any]:
        res = self.adapter.execute(self.sql, self.params)
        return {
            "success": res.success,
            "meta": res._meta
        }

    def raw(self) -> List[List[Any]]:
        res = self.adapter.execute(self.sql, self.params)
        rows = res.fetchall()
        return [list(r.values()) for r in rows]


class D1Cursor:
    """
    Cursor interface adapter allowing existing database queries to execute seamlessly.
    """
    def __init__(self, adapter: "CloudflareD1DatabaseAdapter"):
        self.adapter = adapter
        self._last_result: Optional[D1QueryResult] = None

    def execute(self, sql: str, params: Optional[Union[Tuple, List]] = None) -> "D1Cursor":
        self._last_result = self.adapter.execute(sql, params)
        return self

    def executemany(self, sql: str, seq_of_params: List[Union[Tuple, List]]) -> "D1Cursor":
        for p in seq_of_params:
            self.execute(sql, p)
        return self

    def fetchone(self) -> Optional[Dict[str, Any]]:
        if self._last_result:
            return self._last_result.fetchone()
        return None

    def fetchall(self) -> List[Dict[str, Any]]:
        if self._last_result:
            return self._last_result.fetchall()
        return []

    @property
    def rowcount(self) -> int:
        return self._last_result.rowcount if self._last_result else 0

    @property
    def lastrowid(self) -> Optional[int]:
        return self._last_result.lastrowid if self._last_result else None


class CloudflareD1DatabaseAdapter:
    """
    Cloudflare D1 Database Adapter.
    Supports:
    1. HTTP REST API mode (using official CF D1 v4 endpoint)
    2. Cloudflare Worker binding mode (when running inside worker environment)
    3. Isolated Local/Test Engine mode (for testing without network dependencies)
    """
    def __init__(
        self,
        account_id: Optional[str] = None,
        database_id: Optional[str] = None,
        api_token: Optional[str] = None,
        worker_env: Optional[Any] = None,
        test_mode: bool = False,
        test_db_path: Optional[str] = None
    ):
        self.account_id = account_id or os.getenv("CF_ACCOUNT_ID")
        self.database_id = database_id or os.getenv("CF_D1_DATABASE_ID")
        self.api_token = api_token or os.getenv("CF_API_TOKEN")
        self.worker_env = worker_env
        self.test_mode = test_mode or bool(os.getenv("CF_D1_TEST_MODE", "0") == "1")
        
        # Test engine initialization for deterministic verification
        self._test_conn: Optional[sqlite3.Connection] = None
        if self.test_mode or (not self.worker_env and not (self.account_id and self.database_id and self.api_token)):
            path = test_db_path or ":memory:"
            self._test_conn = sqlite3.connect(path, timeout=30.0)
            self._test_conn.execute("PRAGMA foreign_keys=ON;")
            self._test_conn.row_factory = sqlite3.Row

    def prepare(self, sql: str) -> D1PreparedStatement:
        return D1PreparedStatement(self, sql)

    def cursor(self) -> D1Cursor:
        return D1Cursor(self)

    def execute(self, sql: str, params: Optional[Union[Tuple, List, Dict]] = None) -> D1QueryResult:
        # 1. Test / Local Engine Mode
        if self._test_conn is not None:
            cur = self._test_conn.cursor()
            p = list(params) if params is not None else []
            cur.execute(sql, p)
            rows = []
            if cur.description:
                col_names = [d[0] for d in cur.description]
                for r in cur.fetchall():
                    rows.append({col_names[i]: r[i] for i in range(len(col_names))})
            meta = {
                "changes": cur.rowcount if cur.rowcount >= 0 else 0,
                "last_row_id": cur.lastrowid
            }
            return D1QueryResult(rows, meta, success=True)

        # 2. Worker Binding Mode (when running inside Cloudflare Python Worker)
        if self.worker_env and hasattr(self.worker_env, "DB"):
            p = list(params) if params is not None else []
            stmt = self.worker_env.DB.prepare(sql)
            if p:
                stmt = stmt.bind(*p)
            res = stmt.all()
            results = res.get("results", []) if isinstance(res, dict) else getattr(res, "results", [])
            meta = res.get("meta", {}) if isinstance(res, dict) else getattr(res, "meta", {})
            success = res.get("success", True) if isinstance(res, dict) else getattr(res, "success", True)
            return D1QueryResult(
                results=results,
                meta=meta,
                success=success
            )

        # 3. Cloudflare D1 HTTP REST API Mode
        if not (self.account_id and self.database_id and self.api_token):
            raise ValueError("Cloudflare D1 credentials incomplete. Set CF_ACCOUNT_ID, CF_D1_DATABASE_ID, and CF_API_TOKEN.")

        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/d1/database/{self.database_id}/query"
        payload = json.dumps({
            "sql": sql,
            "params": list(params) if params is not None else []
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if not data.get("success"):
                    errors = data.get("errors", [])
                    raise RuntimeError(f"Cloudflare D1 query error: {errors}")
                first_res = data["result"][0] if data.get("result") else {}
                return D1QueryResult(
                    results=first_res.get("results", []),
                    meta=first_res.get("meta", {}),
                    success=first_res.get("success", True)
                )
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            raise RuntimeError(f"Cloudflare D1 HTTP error {e.code}: {err_body}")

    def batch(self, statements: List[Union[str, D1PreparedStatement]]) -> List[D1QueryResult]:
        results = []
        for stmt in statements:
            if isinstance(stmt, D1PreparedStatement):
                results.append(self.execute(stmt.sql, stmt.params))
            else:
                results.append(self.execute(stmt))
        return results

    def commit(self):
        if self._test_conn:
            self._test_conn.commit()

    def rollback(self):
        if self._test_conn:
            self._test_conn.rollback()

    def close(self):
        if self._test_conn:
            self._test_conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        return False


def get_db(adapter: Optional[str] = None, **kwargs):
    """
    Returns database connection or adapter based on DB_ADAPTER setting.
    Defaults to local SQLite, preserving 100% of existing behavior and data.
    When running inside a Cloudflare Python Worker, automatically binds to worker_env.DB.
    """
    # 1. Check if worker_env was passed explicitly or via request ContextVar
    worker_env = kwargs.get("worker_env")
    if worker_env is None:
        try:
            from .main import current_worker_env
            worker_env = current_worker_env.get()
        except Exception:
            pass

    # 2. If running inside Cloudflare Worker with D1 binding and no explicit adapter override
    if worker_env and hasattr(worker_env, "DB") and adapter is None:
        return CloudflareD1DatabaseAdapter(worker_env=worker_env, **kwargs)

    chosen = (adapter or os.getenv("DB_ADAPTER", "sqlite")).lower()

    if chosen == "sqlite":
        db_file = kwargs.get("db_path", DB_PATH)
        conn = sqlite3.connect(db_file, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.row_factory = sqlite3.Row
        return conn
    elif chosen == "d1":
        return CloudflareD1DatabaseAdapter(worker_env=worker_env, **kwargs)
    else:
        raise ValueError(f"Unsupported DB_ADAPTER '{chosen}'. Supported: 'sqlite', 'd1'.")


def init_db(conn: Optional[Any] = None, adapter: Optional[str] = None, **kwargs):
    """
    Initializes all 18 tables and constraints.
    Supports both SQLite connections and Cloudflare D1 adapters.
    """
    owns_conn = False
    if conn is None:
        conn = get_db(adapter=adapter, **kwargs)
        owns_conn = True

    cursor = conn.cursor() if hasattr(conn, "cursor") else conn

    # Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        name TEXT,
        picture TEXT,
        created_at TEXT NOT NULL
    )
    """)

    # Active sessions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)

    # OAuth state storage for CSRF validation
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS oauth_states (
        state TEXT PRIMARY KEY,
        action TEXT NOT NULL,
        user_id TEXT,
        expires_at TEXT NOT NULL
    )
    """)

    # Encrypted user tokens for Google & Gmail
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_tokens (
        user_id TEXT PRIMARY KEY,
        access_token_encrypted TEXT NOT NULL,
        refresh_token_encrypted TEXT,
        token_expiry TEXT,
        scopes TEXT,
        gmail_connected INTEGER DEFAULT 0,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)

    # User tasks (isolated per user)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_tasks (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        source TEXT,
        source_email_id TEXT,
        due_date TEXT,
        priority TEXT DEFAULT 'normal',
        completed INTEGER DEFAULT 0,
        workspace TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)

    # User workspaces (isolated per user)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_workspaces (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        description TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)

    # User approvals (isolated per user)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_approvals (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        type TEXT NOT NULL,
        target TEXT NOT NULL,
        subject TEXT NOT NULL,
        reason TEXT NOT NULL,
        risk_level TEXT NOT NULL,
        draft_content TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)

    # User execution traces / activity (isolated per user)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_activity (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        trigger TEXT NOT NULL,
        status TEXT NOT NULL,
        latency TEXT,
        result TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)

    # Conversations (isolated per user & optional workspace)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        workspace_id TEXT,
        title TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)

    # Messages (isolated per conversation & user)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        workspace_id TEXT,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        metadata TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)

    # Workspace Notes (isolated per workspace & user)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_workspace_notes (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (workspace_id) REFERENCES user_workspaces (id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)

    # Calendar Events (isolated per user & optional workspace)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_calendar_events (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        workspace_id TEXT,
        title TEXT NOT NULL,
        event_date TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        category TEXT DEFAULT 'General',
        description TEXT,
        source TEXT DEFAULT 'Scheduled Block',
        external_event_id TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)

    # Study Materials (isolated per user & workspace)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_study_materials (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        filename TEXT NOT NULL,
        content_text TEXT NOT NULL,
        topics_json TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)

    # Revision Plans (isolated per user & workspace)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_revision_plans (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        exam_date TEXT NOT NULL,
        plan_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)

    # User Agent Settings & Preferences for Scheduled Runs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_agent_settings (
        user_id TEXT PRIMARY KEY,
        daily_run_enabled INTEGER DEFAULT 0,
        preferred_time TEXT DEFAULT '08:00',
        timezone TEXT DEFAULT 'UTC',
        permitted_sources TEXT DEFAULT '["gmail","tasks","calendar"]',
        max_duration_seconds INTEGER DEFAULT 120,
        max_tool_steps INTEGER DEFAULT 10,
        kill_switch_enabled INTEGER DEFAULT 0,
        next_run_at TEXT,
        last_run_at TEXT,
        last_run_status TEXT,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)

    # Agent Runs (execution lifecycle & high-level status)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agent_runs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        trigger_type TEXT NOT NULL,
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        total_steps INTEGER DEFAULT 0,
        actions_completed INTEGER DEFAULT 0,
        actions_refused INTEGER DEFAULT 0,
        actions_failed INTEGER DEFAULT 0,
        summary TEXT,
        error_message TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)

    # Agent Run Steps (granular execution audit & policy trace)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agent_run_steps (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        step_number INTEGER NOT NULL,
        step_name TEXT NOT NULL,
        tool_name TEXT,
        tool_parameters TEXT,
        policy_decision TEXT NOT NULL,
        approval_required INTEGER DEFAULT 0,
        status TEXT NOT NULL,
        result TEXT,
        latency_ms TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (run_id) REFERENCES agent_runs (id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)

    # Daily Digests (structured attention summaries)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_digests (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        run_id TEXT,
        digest_date TEXT NOT NULL,
        title TEXT NOT NULL,
        content_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)

    if hasattr(conn, "commit"):
        conn.commit()

    if owns_conn and hasattr(conn, "close"):
        conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at", DB_PATH)
