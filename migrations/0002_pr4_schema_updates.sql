-- Migration 0002: PR #4 schema updates (workspace_shares, gmail_draft_id, embedding)

CREATE TABLE IF NOT EXISTS workspace_shares (
    token TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

ALTER TABLE user_approvals ADD COLUMN gmail_draft_id TEXT;
ALTER TABLE user_workspace_notes ADD COLUMN embedding TEXT;
