-- Cloudflare D1 Migration Rollback Script
-- Version: 0001_rollback
-- SAFETY WARNING: NEVER EXECUTE AGAINST PRODUCTION OR ACTIVE SQLITE DATABASE!
-- This script reverses migration 0001 by dropping all 18 tables in reverse foreign-key dependency order.

DROP INDEX IF EXISTS idx_daily_digests_user_date;
DROP INDEX IF EXISTS idx_agent_run_steps_run_id;
DROP INDEX IF EXISTS idx_agent_runs_user_started;
DROP INDEX IF EXISTS idx_user_rev_plans_user_ws;
DROP INDEX IF EXISTS idx_user_study_mat_user_ws;
DROP INDEX IF EXISTS idx_user_cal_events_user_date;
DROP INDEX IF EXISTS idx_user_ws_notes_ws_user;
DROP INDEX IF EXISTS idx_messages_conv_id;
DROP INDEX IF EXISTS idx_conversations_user_ws;
DROP INDEX IF EXISTS idx_user_activity_user_id;
DROP INDEX IF EXISTS idx_user_approvals_user_status;
DROP INDEX IF EXISTS idx_user_workspaces_user_id;
DROP INDEX IF EXISTS idx_user_tasks_due_date;
DROP INDEX IF EXISTS idx_user_tasks_user_id;
DROP INDEX IF EXISTS idx_sessions_expires_at;
DROP INDEX IF EXISTS idx_sessions_user_id;

DROP TABLE IF EXISTS daily_digests;
DROP TABLE IF EXISTS agent_run_steps;
DROP TABLE IF EXISTS agent_runs;
DROP TABLE IF EXISTS user_agent_settings;
DROP TABLE IF EXISTS user_revision_plans;
DROP TABLE IF EXISTS user_study_materials;
DROP TABLE IF EXISTS user_calendar_events;
DROP TABLE IF EXISTS user_workspace_notes;
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS conversations;
DROP TABLE IF EXISTS user_activity;
DROP TABLE IF EXISTS user_approvals;
DROP TABLE IF EXISTS user_workspaces;
DROP TABLE IF EXISTS user_tasks;
DROP TABLE IF EXISTS user_tokens;
DROP TABLE IF EXISTS oauth_states;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS users;
