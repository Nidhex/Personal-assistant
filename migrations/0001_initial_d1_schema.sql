-- Cloudflare D1 Initial Migration Schema
-- Version: 0001
-- Tables: 18 tables + performance indexes
-- Dialect: SQLite / Cloudflare D1

PRAGMA foreign_keys = ON;

-- 1. Users table
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    picture TEXT,
    created_at TEXT NOT NULL
);

-- 2. Active sessions
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- 3. OAuth state storage for CSRF validation
CREATE TABLE IF NOT EXISTS oauth_states (
    state TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    user_id TEXT,
    expires_at TEXT NOT NULL
);

-- 4. Encrypted user tokens for Google & Gmail
CREATE TABLE IF NOT EXISTS user_tokens (
    user_id TEXT PRIMARY KEY,
    access_token_encrypted TEXT NOT NULL,
    refresh_token_encrypted TEXT,
    token_expiry TEXT,
    scopes TEXT,
    gmail_connected INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- 5. User tasks (isolated per user)
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
);

-- 6. User workspaces (isolated per user)
CREATE TABLE IF NOT EXISTS user_workspaces (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- 7. User approvals (isolated per user)
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
);

-- 8. User execution traces / activity (isolated per user)
CREATE TABLE IF NOT EXISTS user_activity (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    trigger TEXT NOT NULL,
    status TEXT NOT NULL,
    latency TEXT,
    result TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- 9. Conversations (isolated per user & optional workspace)
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    workspace_id TEXT,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- 10. Messages (isolated per conversation & user)
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
);

-- 11. Workspace Notes (isolated per workspace & user)
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
);

-- 12. Calendar Events (isolated per user & optional workspace)
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
);

-- 13. Study Materials (isolated per user & workspace)
CREATE TABLE IF NOT EXISTS user_study_materials (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_text TEXT NOT NULL,
    topics_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- 14. Revision Plans (isolated per user & workspace)
CREATE TABLE IF NOT EXISTS user_revision_plans (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    exam_date TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- 15. User Agent Settings & Preferences for Scheduled Runs
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
);

-- 16. Agent Runs (execution lifecycle & high-level status)
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
);

-- 17. Agent Run Steps (granular execution audit & policy trace)
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
);

-- 18. Daily Digests (structured attention summaries)
CREATE TABLE IF NOT EXISTS daily_digests (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    run_id TEXT,
    digest_date TEXT NOT NULL,
    title TEXT NOT NULL,
    content_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- Performance Indexes for Cloudflare D1 Scanned Rows Optimization
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_user_tasks_user_id ON user_tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_user_tasks_due_date ON user_tasks(user_id, due_date);
CREATE INDEX IF NOT EXISTS idx_user_workspaces_user_id ON user_workspaces(user_id);
CREATE INDEX IF NOT EXISTS idx_user_approvals_user_status ON user_approvals(user_id, status);
CREATE INDEX IF NOT EXISTS idx_user_activity_user_id ON user_activity(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_user_ws ON conversations(user_id, workspace_id);
CREATE INDEX IF NOT EXISTS idx_messages_conv_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_user_ws_notes_ws_user ON user_workspace_notes(workspace_id, user_id);
CREATE INDEX IF NOT EXISTS idx_user_cal_events_user_date ON user_calendar_events(user_id, event_date);
CREATE INDEX IF NOT EXISTS idx_user_study_mat_user_ws ON user_study_materials(user_id, workspace_id);
CREATE INDEX IF NOT EXISTS idx_user_rev_plans_user_ws ON user_revision_plans(user_id, workspace_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_user_started ON agent_runs(user_id, started_at);
CREATE INDEX IF NOT EXISTS idx_agent_run_steps_run_id ON agent_run_steps(run_id);
CREATE INDEX IF NOT EXISTS idx_daily_digests_user_date ON daily_digests(user_id, digest_date);
