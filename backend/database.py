import sqlite3
import os
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data.db"

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

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

    # User Agent Settings & Preferences for Scheduled Runs (opt-in by default)
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

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at", DB_PATH)
