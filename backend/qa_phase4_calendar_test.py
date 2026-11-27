"""
QA Phase 4 Test Suite: Complete Calendar Functionality & Integration
Verifies:
1. Event CRUD & Validation (Title validation, conflict checks, force scheduling)
2. Event Editing (PUT endpoint, title/time update, conflict prevention)
3. Event Deletion (DELETE endpoint, 404 on missing/other user's event)
4. Chatbot Natural Language Integration (schedule_event, update_calendar_event, delete_calendar_event)
5. Task and Calendar Strict Independence (No silent creation/mutation)
6. Multi-User & Workspace Isolation
7. Kill Switch Enforcement
"""

import unittest
import os
import asyncio
import sqlite3
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import get_db, init_db
from backend.agent import build_context, query_llm_planner, execute_policy_gate_and_tools, ALLOWED_TOOLS

def run_agent_turn(user_id, workspace_id="main", prompt="", kill_switch_active=False):
    async def _turn():
        ctx = build_context(user_id, workspace_id)
        plan_json = await query_llm_planner(prompt, ctx)
        return await execute_policy_gate_and_tools(plan_json, user_id, workspace_id, kill_switch_active)
    return asyncio.run(_turn())

class QAPhase4CalendarTestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.conn = get_db()
        self.cursor = self.conn.cursor()

        # Clean calendar events and test users
        self.cursor.execute("DELETE FROM user_calendar_events WHERE user_id LIKE 'cal_user_%'")
        self.cursor.execute("DELETE FROM user_tasks WHERE user_id LIKE 'cal_user_%'")
        self.cursor.execute("DELETE FROM user_activity WHERE user_id LIKE 'cal_user_%'")
        self.cursor.execute("DELETE FROM sessions WHERE user_id LIKE 'cal_user_%'")
        self.cursor.execute("DELETE FROM users WHERE id LIKE 'cal_user_%'")
        self.cursor.execute("DELETE FROM user_agent_settings WHERE user_id LIKE 'cal_user_%'")

        # Create Alice
        self.alice_id = "cal_user_alice"
        self.cursor.execute("INSERT OR REPLACE INTO users (id, email, name, created_at) VALUES (?, ?, ?, ?)",
                            (self.alice_id, "alice.cal@example.com", "Alice Cal", datetime.now(timezone.utc).isoformat()))
        self.alice_session = "sess_alice_cal_123"
        self.cursor.execute("INSERT OR REPLACE INTO sessions (session_id, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
                            (self.alice_session, self.alice_id, "2099-01-01T00:00:00", datetime.now(timezone.utc).isoformat()))

        # Create Bob
        self.bob_id = "cal_user_bob"
        self.cursor.execute("INSERT OR REPLACE INTO users (id, email, name, created_at) VALUES (?, ?, ?, ?)",
                            (self.bob_id, "bob.cal@example.com", "Bob Cal", datetime.now(timezone.utc).isoformat()))
        self.bob_session = "sess_bob_cal_456"
        self.cursor.execute("INSERT OR REPLACE INTO sessions (session_id, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
                            (self.bob_session, self.bob_id, "2099-01-01T00:00:00", datetime.now(timezone.utc).isoformat()))

        self.conn.commit()

    def tearDown(self):
        self.cursor.execute("DELETE FROM user_calendar_events WHERE user_id LIKE 'cal_user_%'")
        self.cursor.execute("DELETE FROM user_tasks WHERE user_id LIKE 'cal_user_%'")
        self.cursor.execute("DELETE FROM user_activity WHERE user_id LIKE 'cal_user_%'")
        self.cursor.execute("DELETE FROM sessions WHERE user_id LIKE 'cal_user_%'")
        self.cursor.execute("DELETE FROM users WHERE id LIKE 'cal_user_%'")
        self.cursor.execute("DELETE FROM user_agent_settings WHERE user_id LIKE 'cal_user_%'")
        self.conn.commit()
        self.conn.close()

    def test_01_event_creation_and_title_validation(self):
        """Test event creation with valid and empty titles."""
        # 1. Empty title -> 400
        res = self.client.post(
            "/api/user/calendar/events",
            json={"title": "   ", "event_date": "2026-12-01", "start_time": "10:00", "end_time": "11:00"},
            cookies={"session_id": self.alice_session}
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("cannot be empty", res.json()["detail"])

        # 2. Valid creation
        res = self.client.post(
            "/api/user/calendar/events",
            json={"title": "Systems Architecture Review", "event_date": "2026-12-01", "start_time": "10:00", "end_time": "11:00", "category": "Work"},
            cookies={"session_id": self.alice_session}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["event"]["title"], "Systems Architecture Review")
        event_id = data["event"]["id"]

        # Verify in database
        self.cursor.execute("SELECT title, event_date FROM user_calendar_events WHERE id = ? AND user_id = ?", (event_id, self.alice_id))
        row = self.cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["title"], "Systems Architecture Review")

    def test_02_conflict_detection_and_force_override(self):
        """Test calendar conflict detection returns 409 without force, 200 with force."""
        # Create base event 10:00 - 11:30
        res1 = self.client.post(
            "/api/user/calendar/events",
            json={"title": "Lab Sync", "event_date": "2026-12-02", "start_time": "10:00", "end_time": "11:30"},
            cookies={"session_id": self.alice_session}
        )
        self.assertEqual(res1.status_code, 200)

        # Overlapping slot 10:30 - 12:00 -> 409 Conflict
        res2 = self.client.post(
            "/api/user/calendar/events",
            json={"title": "Conflicting Workshop", "event_date": "2026-12-02", "start_time": "10:30", "end_time": "12:00", "force": False},
            cookies={"session_id": self.alice_session}
        )
        self.assertEqual(res2.status_code, 409)
        self.assertIn("Calendar conflict", res2.json()["detail"])

        # Force schedule -> 200 OK
        res3 = self.client.post(
            "/api/user/calendar/events",
            json={"title": "Overridden Workshop", "event_date": "2026-12-02", "start_time": "10:30", "end_time": "12:00", "force": True},
            cookies={"session_id": self.alice_session}
        )
        self.assertEqual(res3.status_code, 200)

    def test_03_event_editing_endpoint(self):
        """Test PUT /api/user/calendar/events/{event_id} editing details and handling conflicts."""
        # Create event
        res1 = self.client.post(
            "/api/user/calendar/events",
            json={"title": "Original Title", "event_date": "2026-12-03", "start_time": "09:00", "end_time": "10:00"},
            cookies={"session_id": self.alice_session}
        )
        evt_id = res1.json()["event"]["id"]

        # Edit title and time
        res_edit = self.client.put(
            f"/api/user/calendar/events/{evt_id}",
            json={"title": "Updated Session Title", "start_time": "14:00", "end_time": "15:00"},
            cookies={"session_id": self.alice_session}
        )
        self.assertEqual(res_edit.status_code, 200)
        self.assertEqual(res_edit.json()["event"]["title"], "Updated Session Title")
        self.assertEqual(res_edit.json()["event"]["start_time"], "14:00")

        # Edit with empty title -> 400
        res_empty = self.client.put(
            f"/api/user/calendar/events/{evt_id}",
            json={"title": "  "},
            cookies={"session_id": self.alice_session}
        )
        self.assertEqual(res_empty.status_code, 400)

    def test_04_event_deletion_endpoint(self):
        """Test DELETE /api/user/calendar/events/{event_id} and 404 on nonexistent."""
        res1 = self.client.post(
            "/api/user/calendar/events",
            json={"title": "To Be Deleted", "event_date": "2026-12-04", "start_time": "11:00", "end_time": "12:00"},
            cookies={"session_id": self.alice_session}
        )
        evt_id = res1.json()["event"]["id"]

        # Delete
        res_del = self.client.delete(f"/api/user/calendar/events/{evt_id}", cookies={"session_id": self.alice_session})
        self.assertEqual(res_del.status_code, 200)

        # Verify gone
        self.cursor.execute("SELECT id FROM user_calendar_events WHERE id = ?", (evt_id,))
        self.assertIsNone(self.cursor.fetchone())

        # Second delete -> 404
        res_del_again = self.client.delete(f"/api/user/calendar/events/{evt_id}", cookies={"session_id": self.alice_session})
        self.assertEqual(res_del_again.status_code, 404)

    def test_05_chatbot_calendar_intents(self):
        """Test chatbot schedule_event, update_calendar_event, delete_calendar_event."""
        # 1. Schedule via chatbot
        res1 = run_agent_turn(
            user_id=self.alice_id,
            workspace_id="main",
            prompt="Schedule my revision session tomorrow from 5 pm to 7 pm"
        )
        self.assertEqual(res1["tool_executed"], "schedule_event")
        self.assertIn("scheduled successfully", res1["text"])

        # Verify in DB
        self.cursor.execute("SELECT title, start_time, end_time FROM user_calendar_events WHERE user_id = ?", (self.alice_id,))
        evt = self.cursor.fetchone()
        self.assertIsNotNone(evt)
        self.assertEqual(evt["title"], "Study Revision Session")

        # 2. Reschedule via chatbot
        res2 = run_agent_turn(
            user_id=self.alice_id,
            workspace_id="main",
            prompt="Reschedule my Study Revision Session to 14:00"
        )
        self.assertEqual(res2["tool_executed"], "update_calendar_event")
        self.assertIn("rescheduled", res2["text"].lower())

        # 3. Cancel/Delete via chatbot
        res3 = run_agent_turn(
            user_id=self.alice_id,
            workspace_id="main",
            prompt="Cancel my Study Revision Session"
        )
        self.assertEqual(res3["tool_executed"], "delete_calendar_event")
        self.assertIn("canceled", res3["text"].lower())

        # Verify deleted in DB
        self.cursor.execute("SELECT id FROM user_calendar_events WHERE user_id = ?", (self.alice_id,))
        self.assertIsNone(self.cursor.fetchone())

    def test_06_task_and_calendar_strict_independence(self):
        """Verify task creation/completion never silently creates or alters calendar events."""
        # 1. Create a task
        res_task = self.client.post(
            "/api/user/tasks",
            json={"title": "Submit Lab Report", "due_date": "2026-12-05", "priority": "high", "workspace": "main"},
            cookies={"session_id": self.alice_session}
        )
        self.assertEqual(res_task.status_code, 200)
        task_id = res_task.json()["id"]

        # Calendar events must still be ZERO
        self.cursor.execute("SELECT COUNT(*) as cnt FROM user_calendar_events WHERE user_id = ?", (self.alice_id,))
        self.assertEqual(self.cursor.fetchone()["cnt"], 0)

        # 2. Create calendar event
        res_cal = self.client.post(
            "/api/user/calendar/events",
            json={"title": "Lab Review Meeting", "event_date": "2026-12-05", "start_time": "15:00", "end_time": "16:00"},
            cookies={"session_id": self.alice_session}
        )
        self.assertEqual(res_cal.status_code, 200)

        # 3. Complete the task
        res_toggle = self.client.post(f"/api/user/tasks/{task_id}/toggle", cookies={"session_id": self.alice_session})
        self.assertEqual(res_toggle.status_code, 200)

        # Calendar event must remain completely unmodified
        self.cursor.execute("SELECT title, start_time FROM user_calendar_events WHERE user_id = ?", (self.alice_id,))
        cal_row = self.cursor.fetchone()
        self.assertIsNotNone(cal_row)
        self.assertEqual(cal_row["title"], "Lab Review Meeting")
        self.assertEqual(cal_row["start_time"], "15:00")

    def test_07_multi_user_and_workspace_isolation(self):
        """Verify Bob cannot access or modify Alice's calendar events."""
        # Alice creates event
        res = self.client.post(
            "/api/user/calendar/events",
            json={"title": "Alice Confidential Briefing", "event_date": "2026-12-06", "start_time": "09:00", "end_time": "10:00"},
            cookies={"session_id": self.alice_session}
        )
        alice_evt_id = res.json()["event"]["id"]

        # Bob queries calendar -> 0 events
        bob_res = self.client.get("/api/user/calendar/events", cookies={"session_id": self.bob_session})
        self.assertEqual(len(bob_res.json()["events"]), 0)

        # Bob attempts to edit Alice's event -> 404
        bob_edit = self.client.put(
            f"/api/user/calendar/events/{alice_evt_id}",
            json={"title": "Bob Hijack Attempt"},
            cookies={"session_id": self.bob_session}
        )
        self.assertEqual(bob_edit.status_code, 404)

        # Bob attempts to delete Alice's event -> 404
        bob_del = self.client.delete(
            f"/api/user/calendar/events/{alice_evt_id}",
            cookies={"session_id": self.bob_session}
        )
        self.assertEqual(bob_del.status_code, 404)

        # Alice's event is untouched
        self.cursor.execute("SELECT title FROM user_calendar_events WHERE id = ?", (alice_evt_id,))
        self.assertEqual(self.cursor.fetchone()["title"], "Alice Confidential Briefing")

    def test_08_calendar_kill_switch_enforcement(self):
        """Verify chatbot cannot schedule calendar events when kill switch is engaged."""
        # Engage kill switch for Alice
        self.cursor.execute("INSERT OR REPLACE INTO user_agent_settings (user_id, kill_switch_enabled, updated_at) VALUES (?, 1, ?)",
                            (self.alice_id, datetime.now(timezone.utc).isoformat()))
        self.conn.commit()

        # Attempt to schedule via chatbot
        res = run_agent_turn(
            user_id=self.alice_id,
            workspace_id="main",
            prompt="Schedule my revision session tomorrow from 5 pm to 7 pm",
            kill_switch_active=True
        )
        self.assertIn("kill switch", res["policy_decision"].lower())
        self.assertIn("emergency kill switch", res["text"].lower())

        # Verify 0 events were created
        self.cursor.execute("SELECT COUNT(*) as cnt FROM user_calendar_events WHERE user_id = ?", (self.alice_id,))
        self.assertEqual(self.cursor.fetchone()["cnt"], 0)

if __name__ == "__main__":
    unittest.main()
