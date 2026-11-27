import unittest
import asyncio
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock

from backend.database import get_db, init_db
from backend.scheduler import (
    is_due_for_run,
    acquire_atomic_run_lock,
    release_run_lock,
    run_scheduled_tick,
    DailyRunScheduler
)
from backend.orchestrator import (
    get_or_create_user_settings,
    update_user_settings,
    calculate_next_run,
    execute_daily_run
)
from backend.worker import handle_worker_scheduled_tick

class TestCloudflareCronTriggers(unittest.TestCase):
    def setUp(self):
        init_db()
        with get_db() as conn:
            now = datetime.now(timezone.utc).isoformat()
            # Clean test rows
            conn.execute("DELETE FROM user_agent_settings WHERE user_id LIKE 'cron_test_%'")
            conn.execute("DELETE FROM agent_runs WHERE user_id LIKE 'cron_test_%'")
            conn.execute("DELETE FROM agent_run_steps WHERE user_id LIKE 'cron_test_%'")
            conn.execute("DELETE FROM daily_digests WHERE user_id LIKE 'cron_test_%'")
            conn.execute("DELETE FROM user_tasks WHERE user_id LIKE 'cron_test_%'")
            conn.execute("DELETE FROM user_approvals WHERE user_id LIKE 'cron_test_%'")
            conn.execute("DELETE FROM users WHERE id LIKE 'cron_test_%'")

            # Create test users
            conn.execute("INSERT OR REPLACE INTO users (id, email, name, created_at) VALUES ('cron_test_ny', 'ny@test.local', 'NY User', ?)", (now,))
            conn.execute("INSERT OR REPLACE INTO users (id, email, name, created_at) VALUES ('cron_test_tokyo', 'tokyo@test.local', 'Tokyo User', ?)", (now,))
            conn.execute("INSERT OR REPLACE INTO users (id, email, name, created_at) VALUES ('cron_test_london', 'london@test.local', 'London User', ?)", (now,))
            conn.commit()

    def tearDown(self):
        with get_db() as conn:
            conn.execute("DELETE FROM user_agent_settings WHERE user_id LIKE 'cron_test_%'")
            conn.execute("DELETE FROM agent_runs WHERE user_id LIKE 'cron_test_%'")
            conn.execute("DELETE FROM agent_run_steps WHERE user_id LIKE 'cron_test_%'")
            conn.execute("DELETE FROM daily_digests WHERE user_id LIKE 'cron_test_%'")
            conn.execute("DELETE FROM user_tasks WHERE user_id LIKE 'cron_test_%'")
            conn.execute("DELETE FROM user_approvals WHERE user_id LIKE 'cron_test_%'")
            conn.execute("DELETE FROM users WHERE id LIKE 'cron_test_%'")
            conn.commit()

    def test_01_timezone_handling_and_due_check(self):
        """Verify is_due_for_run correctly respects user timezones and preferred hours."""
        # Setup: New York user (America/New_York) wanting run at 09:00
        # Reference UTC time: 2026-11-27 14:30:00 UTC -> 09:30 AM in New York
        ref_utc = datetime(2026, 11, 27, 14, 30, 0, tzinfo=timezone.utc)

        settings_ny = {
            "user_id": "cron_test_ny",
            "daily_run_enabled": 1,
            "preferred_time": "09:00",
            "timezone": "America/New_York",
            "last_run_at": None,
            "last_run_status": "never_run"
        }
        # In NY it is 09:30 AM, preferred time was 09:00 -> Due!
        self.assertTrue(is_due_for_run(settings_ny, now_utc=ref_utc))

        # Change preferred time to 10:00 AM (in future for NY)
        settings_ny_future = dict(settings_ny, preferred_time="10:00")
        self.assertFalse(is_due_for_run(settings_ny_future, now_utc=ref_utc))

        # Check Tokyo user (Asia/Tokyo, UTC+9): at 14:30 UTC, Tokyo is 23:30 (11:30 PM)
        settings_tokyo = {
            "user_id": "cron_test_tokyo",
            "daily_run_enabled": 1,
            "preferred_time": "08:00",
            "timezone": "Asia/Tokyo",
            "last_run_at": None,
            "last_run_status": "never_run"
        }
        # In Tokyo it is 23:30, preferred time was 08:00 -> Due!
        self.assertTrue(is_due_for_run(settings_tokyo, now_utc=ref_utc))

    def test_02_duplicate_prevention_same_day(self):
        """Verify that a user who has already executed on today's calendar date is not run again."""
        ref_utc = datetime(2026, 11, 27, 14, 30, 0, tzinfo=timezone.utc)
        # Already ran earlier today in NY (at 09:05 AM NY time -> 14:05 UTC)
        earlier_today_utc = datetime(2026, 11, 27, 14, 5, 0, tzinfo=timezone.utc).isoformat()

        settings_ran_today = {
            "user_id": "cron_test_ny",
            "daily_run_enabled": 1,
            "preferred_time": "09:00",
            "timezone": "America/New_York",
            "last_run_at": earlier_today_utc,
            "last_run_status": "completed"
        }
        self.assertFalse(is_due_for_run(settings_ran_today, now_utc=ref_utc))

        # Ran yesterday in NY (2026-11-26) -> Due today!
        yesterday_utc = datetime(2026, 11, 26, 14, 5, 0, tzinfo=timezone.utc).isoformat()
        settings_ran_yesterday = dict(settings_ran_today, last_run_at=yesterday_utc)
        self.assertTrue(is_due_for_run(settings_ran_yesterday, now_utc=ref_utc))

    def test_03_atomic_database_claim_prevents_concurrent_runs(self):
        """Verify that atomic database claim grants lock to only ONE worker when called concurrently."""
        ref_utc = datetime(2026, 11, 27, 14, 30, 0, tzinfo=timezone.utc)
        with get_db() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO user_agent_settings (
                    user_id, daily_run_enabled, preferred_time, timezone, permitted_sources,
                    max_duration_seconds, max_tool_steps, kill_switch_enabled,
                    next_run_at, last_run_at, last_run_status, updated_at
                ) VALUES ('cron_test_ny', 1, '09:00', 'America/New_York', '["tasks"]', 120, 10, 0, NULL, NULL, 'never_run', ?)
            """, (ref_utc.isoformat(),))
            conn.commit()

        # Two worker connections attempting to claim the user simultaneously
        conn1 = get_db()
        conn2 = get_db()

        claim1 = acquire_atomic_run_lock(conn1, "cron_test_ny", now_utc=ref_utc)
        claim2 = acquire_atomic_run_lock(conn2, "cron_test_ny", now_utc=ref_utc)

        conn1.close()
        conn2.close()

        # Exactly ONE worker must succeed, the other MUST fail
        self.assertTrue(claim1, "Worker 1 should have acquired the atomic lock")
        self.assertFalse(claim2, "Worker 2 should have been blocked by the atomic lock")

    def test_04_stale_lock_recovery(self):
        """Verify that a crashed/stale lock older than 10 minutes is automatically recovered."""
        stale_time_utc = datetime(2026, 11, 27, 14, 0, 0, tzinfo=timezone.utc)
        current_time_utc = datetime(2026, 11, 27, 14, 25, 0, tzinfo=timezone.utc) # 25 minutes later

        with get_db() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO user_agent_settings (
                    user_id, daily_run_enabled, preferred_time, timezone, permitted_sources,
                    max_duration_seconds, max_tool_steps, kill_switch_enabled,
                    next_run_at, last_run_at, last_run_status, updated_at
                ) VALUES ('cron_test_ny', 1, '09:00', 'America/New_York', '["tasks"]', 120, 10, 0, NULL, ?, 'running', ?)
            """, (stale_time_utc.isoformat(), stale_time_utc.isoformat()))
            conn.commit()

        # Attempt to claim stale lock
        with get_db() as conn:
            recovered = acquire_atomic_run_lock(conn, "cron_test_ny", now_utc=current_time_utc)
            self.assertTrue(recovered, "Stale lock > 10 minutes should be reclaimed")

    def test_05_kill_switch_preservation_during_scheduled_run(self):
        """Verify emergency kill switch halts scheduled run immediately and logs audit step."""
        ref_utc = datetime(2026, 11, 27, 14, 30, 0, tzinfo=timezone.utc)
        with get_db() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO user_agent_settings (
                    user_id, daily_run_enabled, preferred_time, timezone, permitted_sources,
                    max_duration_seconds, max_tool_steps, kill_switch_enabled,
                    next_run_at, last_run_at, last_run_status, updated_at
                ) VALUES ('cron_test_ny', 1, '09:00', 'America/New_York', '["tasks"]', 120, 10, 1, NULL, NULL, 'never_run', ?)
            """, (ref_utc.isoformat(),))
            conn.commit()

        # Run scheduled tick with bounded timeout
        tick_result = asyncio.run(asyncio.wait_for(run_scheduled_tick(now_utc=ref_utc), timeout=10.0))
        self.assertTrue(tick_result["success"])
        self.assertEqual(tick_result["runs_triggered"], 1)
        self.assertEqual(tick_result["triggered_details"][0]["status"], "stopped_by_kill_switch")

        # Verify database record
        with get_db() as conn:
            run = conn.execute("SELECT * FROM agent_runs WHERE user_id = 'cron_test_ny' ORDER BY started_at DESC LIMIT 1").fetchone()
            self.assertIsNotNone(run)
            self.assertEqual(run["status"], "stopped_by_kill_switch")

    def test_06_scheduled_execution_records_history_and_digest(self):
        """Verify successful scheduled execution generates run record, step traces, and Daily Digest."""
        ref_utc = datetime(2026, 11, 27, 14, 30, 0, tzinfo=timezone.utc)
        with get_db() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO user_agent_settings (
                    user_id, daily_run_enabled, preferred_time, timezone, permitted_sources,
                    max_duration_seconds, max_tool_steps, kill_switch_enabled,
                    next_run_at, last_run_at, last_run_status, updated_at
                ) VALUES ('cron_test_london', 1, '12:00', 'Europe/London', '["tasks"]', 120, 10, 0, NULL, NULL, 'never_run', ?)
            """, (ref_utc.isoformat(),))
            # Insert a task for London user
            conn.execute("""
                INSERT INTO user_tasks (id, user_id, title, due_date, priority, completed, created_at)
                VALUES ('t_london_1', 'cron_test_london', 'Review Cloudflare Cron Spec', '2026-11-27', 'high', 0, ?)
            """, (ref_utc.isoformat(),))
            conn.commit()

        # Run scheduled tick with bounded timeout
        tick_result = asyncio.run(asyncio.wait_for(run_scheduled_tick(now_utc=ref_utc), timeout=10.0))
        self.assertTrue(tick_result["success"])
        self.assertEqual(tick_result["runs_triggered"], 1)
        self.assertIn(tick_result["triggered_details"][0]["status"], ["completed", "completed_with_warnings"])

        # Verify agent_runs, agent_run_steps, and daily_digests records
        with get_db() as conn:
            run = conn.execute("SELECT * FROM agent_runs WHERE user_id = 'cron_test_london'").fetchone()
            self.assertIsNotNone(run)
            self.assertIn(run["status"], ["completed", "completed_with_warnings"])

            steps = conn.execute("SELECT * FROM agent_run_steps WHERE run_id = ?", (run["id"],)).fetchall()
            self.assertTrue(len(steps) >= 3, f"Expected at least 3 audited steps, found {len(steps)}")

            digest = conn.execute("SELECT * FROM daily_digests WHERE user_id = 'cron_test_london'").fetchone()
            self.assertIsNotNone(digest)
            self.assertTrue("Daily Briefing" in digest["title"] or "Daily Digest" in digest["title"])

    def test_07_cloudflare_worker_scheduled_handler_integration(self):
        """Verify handle_worker_scheduled_tick integrates directly with Cloudflare Cron Trigger."""
        class MockWorkerEnv:
            pass

        mock_env = MockWorkerEnv()
        res = asyncio.run(asyncio.wait_for(handle_worker_scheduled_tick(env=mock_env), timeout=10.0))
        self.assertTrue(res["success"])
        self.assertIn("users_checked", res)

    def test_08_local_scheduler_background_service_start_stop(self):
        """Verify local DailyRunScheduler service starts and stops cleanly with bounded execution."""
        sched = DailyRunScheduler()
        try:
            sched.start(force=True)
            self.assertTrue(sched._running)
        finally:
            sched.stop()
        self.assertFalse(sched._running)

    def test_09_concurrency_lock_released_in_finally_on_error(self):
        """Verify lock is guaranteed to be released even if execution raises an unexpected exception."""
        ref_utc = datetime(2026, 11, 27, 14, 30, 0, tzinfo=timezone.utc)
        with get_db() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO user_agent_settings (
                    user_id, daily_run_enabled, preferred_time, timezone, permitted_sources,
                    max_duration_seconds, max_tool_steps, kill_switch_enabled,
                    next_run_at, last_run_at, last_run_status, updated_at
                ) VALUES ('cron_test_ny', 1, '09:00', 'America/New_York', '["tasks"]', 120, 10, 0, NULL, NULL, 'never_run', ?)
            """, (ref_utc.isoformat(),))
            conn.commit()

        # Mock execute_daily_run to fail catastrophically
        with patch("backend.scheduler.execute_daily_run", side_effect=RuntimeError("Simulated worker failure")):
            tick_result = asyncio.run(asyncio.wait_for(run_scheduled_tick(now_utc=ref_utc), timeout=10.0))
            self.assertFalse(tick_result["success"])
            self.assertEqual(len(tick_result["errors"]), 1)

        # Verify database lock was released in finally block and status is 'failed', NOT left stuck in 'running'
        with get_db() as conn:
            row = conn.execute("SELECT last_run_status FROM user_agent_settings WHERE user_id = 'cron_test_ny'").fetchone()
            self.assertEqual(row["last_run_status"], "failed", "Lock status should be 'failed', not 'running'")

if __name__ == "__main__":
    unittest.main()
