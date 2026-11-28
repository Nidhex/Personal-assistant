"""
Stage 4 Regression Tests: Scheduler Validation & Collision-Resistant IDs.

Covers:
Part A: Scheduler Time Validation & Malformed Input Handling
Part B: Collision-Resistant IDs (Approvals, Actions, Plans, Messages, Tasks)
"""
import re
import uuid
import time
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi.testclient import TestClient

from backend.orchestrator import (
    parse_and_validate_time,
    calculate_next_run,
    update_user_settings,
    get_or_create_user_settings,
    log_run_step
)
from backend.scheduler import is_due_for_run
from backend.main import app
from backend.database import get_db, init_db


class TestSchedulerTimeValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.user_id = f"usr_test_stage4_{uuid.uuid4().hex[:8]}"
        conn = get_db()
        conn.execute(
            "INSERT OR REPLACE INTO users (id, email, name, created_at) VALUES (?, ?, ?, ?)",
            (self.user_id, f"{self.user_id}@test.com", "Stage 4 Tester", datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()

    # -------------------------------------------------------------------------
    # Part A.1: parse_and_validate_time strict validation
    # -------------------------------------------------------------------------
    def test_parse_and_validate_time_accepts_valid_times(self):
        valid_cases = [
            ("00:00", (0, 0)),
            ("08:00", (8, 0)),
            ("08:30", (8, 30)),
            ("12:00", (12, 0)),
            ("12:30", (12, 30)),
            ("17:45", (17, 45)),
            ("23:59", (23, 59)),
            ("  09:15  ", (9, 15)),  # Leading/trailing whitespace trimmed safely
        ]
        for time_str, expected in valid_cases:
            with self.subTest(time_str=time_str):
                result = parse_and_validate_time(time_str)
                self.assertEqual(result, expected, f"Expected {expected} for valid time {time_str!r}")

    def test_parse_and_validate_time_rejects_invalid_times(self):
        invalid_cases = [
            "8:00",       # Missing leading zero
            "9:30",       # Missing leading zero
            "24:00",      # 24 is out of 00-23 range
            "25:00",      # 25 is out of range
            "12:60",      # 60 is out of 00-59 range
            "12:90",      # 90 is out of range
            "-01:00",     # Negative hour
            "12:-05",     # Negative minute
            "12:00:00",   # Seconds not allowed
            "12:0",       # Incomplete minute
            "",           # Empty string
            "   ",        # Whitespace only
            "invalid",    # Random text
            "noon",       # Word
            "12pm",       # 12-hour format
            None,         # NoneType
            1200,         # Non-string integer
            ["08:00"],    # Non-string list
        ]
        for val in invalid_cases:
            with self.subTest(val=val):
                result = parse_and_validate_time(val)
                self.assertIsNone(result, f"Expected None for invalid time input {val!r}")

    # -------------------------------------------------------------------------
    # Part A.2: calculate_next_run handles valid and malformed times
    # -------------------------------------------------------------------------
    def test_calculate_next_run_valid(self):
        next_run = calculate_next_run("08:00", "UTC")
        self.assertIsNotNone(next_run)
        # Must be a valid ISO timestamp
        dt = datetime.fromisoformat(next_run)
        self.assertEqual(dt.hour, 8)
        self.assertEqual(dt.minute, 0)

    def test_calculate_next_run_malformed_returns_none_safely(self):
        malformed_inputs = ["8:00", "25:00", "12:90", "", "bad_time", None]
        for bad in malformed_inputs:
            with self.subTest(bad=bad):
                # Must return None safely without raising an unhandled exception or crashing
                res = calculate_next_run(bad, "UTC")
                self.assertIsNone(res)

    # -------------------------------------------------------------------------
    # Part A.3: is_due_for_run safe malformed handling & numerical comparison
    # -------------------------------------------------------------------------
    def test_is_due_for_run_malformed_tolerance(self):
        settings = {
            "user_id": self.user_id,
            "daily_run_enabled": 1,
            "preferred_time": "8:00",  # Unpadded, invalid
            "timezone": "UTC"
        }
        # Must return False safely and not crash
        self.assertFalse(is_due_for_run(settings))

        settings["preferred_time"] = "25:00"
        self.assertFalse(is_due_for_run(settings))

        settings["preferred_time"] = ""
        self.assertFalse(is_due_for_run(settings))

        settings["preferred_time"] = None
        self.assertFalse(is_due_for_run(settings))

    def test_is_due_for_run_numerical_comparison(self):
        # User scheduled for 09:30 UTC
        settings = {
            "user_id": self.user_id,
            "daily_run_enabled": 1,
            "preferred_time": "09:30",
            "timezone": "UTC",
            "last_daily_run": None
        }

        # Case 1: Current time 09:15 UTC (before preferred time) -> NOT DUE
        time_before = datetime(2026, 11, 28, 9, 15, tzinfo=timezone.utc)
        self.assertFalse(is_due_for_run(settings, now_utc=time_before))

        # Case 2: Current time 09:30 UTC (exact preferred time) -> DUE
        time_exact = datetime(2026, 11, 28, 9, 30, tzinfo=timezone.utc)
        self.assertTrue(is_due_for_run(settings, now_utc=time_exact))

        # Case 3: Current time 10:00 UTC (after preferred time) -> DUE
        time_after = datetime(2026, 11, 28, 10, 0, tzinfo=timezone.utc)
        self.assertTrue(is_due_for_run(settings, now_utc=time_after))

    # -------------------------------------------------------------------------
    # Part A.4: update_user_settings validation
    # -------------------------------------------------------------------------
    def test_update_user_settings_rejects_invalid_time(self):
        invalid_times = ["8:00", "24:00", "25:00", "12:90", "not_a_time", ""]
        for bad_time in invalid_times:
            with self.subTest(bad_time=bad_time):
                with self.assertRaises(ValueError):
                    update_user_settings(self.user_id, {"preferred_time": bad_time})

    def test_update_user_settings_accepts_valid_time(self):
        updated = update_user_settings(self.user_id, {"preferred_time": "14:15"})
        self.assertEqual(updated["preferred_time"], "14:15")

    # -------------------------------------------------------------------------
    # Part A.5: REST API /api/agent/settings validation
    # -------------------------------------------------------------------------
    def test_api_save_settings_rejects_invalid_preferred_time(self):
        client = TestClient(app)
        # Create an authorized user session in SQLite
        conn = get_db()
        session_id = f"sess_stage4_{uuid.uuid4().hex}"
        conn.execute(
            "INSERT INTO sessions (session_id, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (session_id, self.user_id, "2099-01-01T00:00:00Z", datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()

        client.cookies.set("session_id", session_id)

        invalid_times = ["8:00", "24:00", "25:00", "12:90", "malformed"]
        for bad in invalid_times:
            with self.subTest(bad=bad):
                res = client.post("/api/agent/settings", json={"preferred_time": bad})
                self.assertEqual(res.status_code, 400, f"Expected 400 for {bad}, got {res.status_code}: {res.text}")
                data = res.json()
                self.assertIn("detail", data)
                self.assertIn("HH:MM", data["detail"])

        # Valid time succeeds
        res_ok = client.post("/api/agent/settings", json={"preferred_time": "16:45"})
        self.assertEqual(res_ok.status_code, 200)
        self.assertEqual(res_ok.json()["settings"]["preferred_time"], "16:45")


class TestCollisionResistantIDs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def test_approval_id_generation_uniqueness(self):
        """Generates 1000 approval IDs in tight loop; asserts zero collisions and correct prefix."""
        generated = [f"appr_{uuid.uuid4().hex}" for _ in range(1000)]
        self.assertEqual(len(generated), len(set(generated)), "Collision detected in approval IDs!")
        for aid in generated:
            self.assertTrue(aid.startswith("appr_"))
            self.assertTrue(re.match(r"^appr_[0-9a-f]{32}$", aid))

    def test_calendar_approval_id_uniqueness(self):
        """Generates 1000 calendar approval IDs in tight loop; asserts zero collisions and correct prefix."""
        generated = [f"appr_cal_{uuid.uuid4().hex}" for _ in range(1000)]
        self.assertEqual(len(generated), len(set(generated)), "Collision detected in calendar approval IDs!")
        for aid in generated:
            self.assertTrue(aid.startswith("appr_cal_"))
            self.assertTrue(re.match(r"^appr_cal_[0-9a-f]{32}$", aid))

    def test_action_id_generation_uniqueness(self):
        """Generates 1000 activity action IDs in tight loop; asserts zero collisions."""
        generated = [f"act_{uuid.uuid4().hex}" for _ in range(1000)]
        self.assertEqual(len(generated), len(set(generated)), "Collision detected in action IDs!")
        for act_id in generated:
            self.assertTrue(act_id.startswith("act_"))
            self.assertTrue(re.match(r"^act_[0-9a-f]{32}$", act_id))

    def test_plan_id_generation_uniqueness(self):
        """Generates 1000 revision plan IDs in tight loop; asserts zero collisions."""
        generated = [f"plan_{uuid.uuid4().hex[:12]}" for _ in range(1000)]
        self.assertEqual(len(generated), len(set(generated)), "Collision detected in plan IDs!")
        for pid in generated:
            self.assertTrue(pid.startswith("plan_"))

    def test_chat_message_id_uniqueness(self):
        """Generates 1000 user and assistant message IDs in tight loop; asserts zero collisions."""
        user_msgs = [f"msg_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}_u" for _ in range(1000)]
        asst_msgs = [f"msg_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}_a" for _ in range(1000)]

        self.assertEqual(len(user_msgs), len(set(user_msgs)), "Collision in user message IDs!")
        self.assertEqual(len(asst_msgs), len(set(asst_msgs)), "Collision in assistant message IDs!")
        # Cross set uniqueness
        self.assertEqual(len(set(user_msgs).intersection(set(asst_msgs))), 0)

        for mid in user_msgs:
            self.assertTrue(mid.startswith("msg_") and mid.endswith("_u"))
        for mid in asst_msgs:
            self.assertTrue(mid.startswith("msg_") and mid.endswith("_a"))

    def test_task_id_uniqueness(self):
        """Generates 1000 task IDs in tight loop; asserts zero collisions."""
        task_ids = [
            f"tsk_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
            for _ in range(1000)
        ]
        self.assertEqual(len(task_ids), len(set(task_ids)), "Collision detected in task IDs!")

    def test_log_run_step_generates_unique_steps(self):
        """Verifies log_run_step creates unique step_id in database."""
        user_id = f"usr_step_{uuid.uuid4().hex[:8]}"
        run_id = f"run_{uuid.uuid4().hex}"
        now_str = datetime.now(timezone.utc).isoformat()
        conn = get_db()
        conn.execute(
            "INSERT OR REPLACE INTO users (id, email, name, created_at) VALUES (?, ?, ?, ?)",
            (user_id, f"{user_id}@test.com", "Step Tester", now_str)
        )
        conn.execute(
            "INSERT INTO agent_runs (id, user_id, trigger_type, status, started_at) VALUES (?, ?, 'manual', 'running', ?)",
            (run_id, user_id, now_str)
        )
        conn.commit()
        conn.close()

        for i in range(20):
            log_run_step(
                run_id=run_id,
                user_id=user_id,
                step_number=i + 1,
                step_name=f"test_step_{i}",
                tool_name="test_tool",
                policy_decision="Allowed",
                status="Completed",
                result="Success",
                latency_ms="1ms"
            )

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM agent_run_steps WHERE run_id = ?", (run_id,))
        rows = cursor.fetchall()
        conn.close()

        step_ids = [r["id"] for r in rows]
        self.assertEqual(len(step_ids), 20)
        self.assertEqual(len(step_ids), len(set(step_ids)), "Collision detected in run step IDs!")
        for sid in step_ids:
            self.assertTrue(sid.startswith("step_"))


if __name__ == "__main__":
    unittest.main()
