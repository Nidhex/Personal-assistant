import sqlite3
import os
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
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

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at", DB_PATH)
