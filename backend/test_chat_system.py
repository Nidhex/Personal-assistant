import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import json
import sqlite3
import asyncio
from datetime import datetime, timezone, timedelta

# Import database and agent modules
from backend.database import DB_PATH, get_db, init_db
from backend.agent import (
    build_context,
    query_llm_planner,
    execute_policy_gate_and_tools,
    detect_calendar_conflicts,
    parse_time_to_minutes,
    minutes_to_time_str,
    parse_relative_date,
    is_valid_youtube_url,
    parse_youtube_transcript_text,
    extract_topics_from_text
)

def setup_test_data():
    init_db()
    with get_db() as conn:
        now = datetime.now(timezone.utc).isoformat()
        # Create two test users if not exist
        conn.execute("INSERT OR REPLACE INTO users (id, email, name, created_at) VALUES ('test_user_a', 'user_a@example.com', 'Alice', ?)", (now,))
        conn.execute("INSERT OR REPLACE INTO users (id, email, name, created_at) VALUES ('test_user_b', 'user_b@example.com', 'Bob', ?)", (now,))

        # Workspaces for User A
        conn.execute("INSERT OR REPLACE INTO user_workspaces (id, user_id, name, type, description, created_at) VALUES ('ws_a_1', 'test_user_a', 'Alpha Project', 'project', 'Alpha description', ?)", (now,))
        conn.execute("INSERT OR REPLACE INTO user_workspaces (id, user_id, name, type, description, created_at) VALUES ('ws_a_2', 'test_user_a', 'Beta Study', 'study', 'Beta description', ?)", (now,))

        # Workspace for User B
        conn.execute("INSERT OR REPLACE INTO user_workspaces (id, user_id, name, type, description, created_at) VALUES ('ws_b_1', 'test_user_b', 'Gamma Secret', 'project', 'Gamma description', ?)", (now,))

        # Clean prior test rows for these users
        conn.execute("DELETE FROM user_workspace_notes WHERE user_id IN ('test_user_a', 'test_user_b')")
        conn.execute("DELETE FROM user_tasks WHERE user_id IN ('test_user_a', 'test_user_b')")
        conn.execute("DELETE FROM user_calendar_events WHERE user_id IN ('test_user_a', 'test_user_b')")
        conn.execute("DELETE FROM user_revision_plans WHERE user_id IN ('test_user_a', 'test_user_b')")
        conn.execute("DELETE FROM user_study_materials WHERE user_id IN ('test_user_a', 'test_user_b')")
        conn.execute("DELETE FROM user_approvals WHERE user_id IN ('test_user_a', 'test_user_b')")
        conn.execute("DELETE FROM user_activity WHERE user_id IN ('test_user_a', 'test_user_b')")

        # Add notes in Workspace A1
        conn.execute("INSERT INTO user_workspace_notes (id, workspace_id, user_id, title, content, created_at, updated_at) VALUES ('note_1', 'ws_a_1', 'test_user_a', 'Alpha Roadmap', 'Launch Alpha in Q4 with high security.', ?, ?)", (now, now))
        conn.execute("INSERT INTO user_workspace_notes (id, workspace_id, user_id, title, content, created_at, updated_at) VALUES ('note_2', 'ws_b_1', 'test_user_b', 'Secret B Code', 'Top secret code for Bob only.', ?, ?)", (now, now))

        # Add task in Workspace A1
        conn.execute("INSERT INTO user_tasks (id, user_id, title, source, due_date, priority, completed, workspace, created_at) VALUES ('task_1', 'test_user_a', 'Review Alpha specifications', 'Manual', 'Tomorrow', 'high', 0, 'Alpha Project', ?)", (now,))
        conn.execute("INSERT INTO user_tasks (id, user_id, title, source, due_date, priority, completed, workspace, created_at) VALUES ('task_2', 'test_user_b', 'Bob task confidential', 'Manual', 'Today', 'normal', 0, 'Gamma Secret', ?)", (now,))

        conn.commit()

def test_context_isolation():
    setup_test_data()
    # Context for User A in ws_a_1
    ctx_a1 = build_context(user_id='test_user_a', workspace_id='ws_a_1', conversation_id='conv_test')
    assert any("Alpha Roadmap" in n["title"] for n in ctx_a1["notes"]), "Alice's ws_a_1 notes should be present"
    assert any("Review Alpha specifications" in t["title"] for t in ctx_a1["tasks"]), "Alice's ws_a_1 tasks should be present"

    # Check that Bob's data NEVER appears in Alice's context
    assert not any("Secret B Code" in n["title"] for n in ctx_a1["notes"]), "Bob's notes leaked into Alice's context!"
    assert not any("Bob task confidential" in t["title"] for t in ctx_a1["tasks"]), "Bob's tasks leaked into Alice's context!"

    # Context for User A in ws_a_2 (different workspace of Alice)
    ctx_a2 = build_context(user_id='test_user_a', workspace_id='ws_a_2', conversation_id='conv_test')
    assert not any("Alpha Roadmap" in n["title"] for n in ctx_a2["notes"]), "ws_a_1 notes leaked into ws_a_2!"
    assert not any("Review Alpha specifications" in t["title"] for t in ctx_a2["tasks"]), "ws_a_1 tasks leaked into ws_a_2!"
    print("PASS: test_context_isolation")

def test_database_multi_user_isolation():
    setup_test_data()
    with get_db() as conn:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("DELETE FROM conversations WHERE user_id IN ('test_user_a', 'test_user_b')")
        conn.execute("INSERT INTO conversations (id, user_id, workspace_id, title, created_at, updated_at) VALUES ('conv_a_1', 'test_user_a', 'ws_a_1', 'Alice Alpha Chat', ?, ?)", (now, now))
        conn.execute("INSERT INTO conversations (id, user_id, workspace_id, title, created_at, updated_at) VALUES ('conv_b_1', 'test_user_b', 'ws_b_1', 'Bob Private Chat', ?, ?)", (now, now))
        conn.commit()

        a_convs = conn.execute("SELECT id, title FROM conversations WHERE user_id = 'test_user_a'").fetchall()
        assert len(a_convs) == 1
        assert a_convs[0]['id'] == 'conv_a_1'

        b_as_a = conn.execute("SELECT id FROM conversations WHERE id = 'conv_b_1' AND user_id = 'test_user_a'").fetchone()
        assert b_as_a is None
    print("PASS: test_database_multi_user_isolation")

async def test_policy_gate_kill_switch_async():
    setup_test_data()
    model_output = json.dumps({
        "action": {
            "tool": "create_task",
            "parameters": {"title": "Test kill switch task"}
        },
        "response": "Creating task."
    })

    result = await execute_policy_gate_and_tools(
        model_output=model_output,
        user_id='test_user_a',
        workspace_id='ws_a_1',
        kill_switch_active=True
    )
    assert "Refused" in result["policy_decision"]
    assert "Emergency Kill Switch" in result["policy_decision"]
    assert result["tool_executed"] is None
    print("PASS: test_policy_gate_kill_switch")

async def test_policy_gate_approval_staging_async():
    setup_test_data()
    model_output = json.dumps({
        "action": {
            "tool": "propose_draft",
            "parameters": {
                "target": "client@example.com",
                "subject": "Project Proposal",
                "draft_content": "Here is the proposal."
            }
        },
        "response": "I have staged an email draft for your review."
    })

    result = await execute_policy_gate_and_tools(
        model_output=model_output,
        user_id='test_user_a',
        workspace_id='ws_a_1',
        kill_switch_active=False
    )
    assert result["approval_required"] is True
    assert result["tool_executed"] == "propose_draft"

    with get_db() as conn:
        row = conn.execute("SELECT * FROM user_approvals WHERE user_id = 'test_user_a' AND status = 'pending' ORDER BY created_at DESC LIMIT 1").fetchone()
        assert row is not None
        assert row['target'] == 'client@example.com'
    print("PASS: test_policy_gate_approval_staging")

async def test_tasks_lifecycle_and_deduplication_async():
    setup_test_data()
    # 1. Create task
    model_output = json.dumps({
        "action": {
            "tool": "create_task",
            "parameters": {
                "title": "Complete Math Assignment",
                "due_date": "tomorrow",
                "priority": "high"
            }
        },
        "response": "Creating task."
    })
    res1 = await execute_policy_gate_and_tools(model_output, 'test_user_a', 'ws_a_1', False)
    assert res1["tool_executed"] == "create_task"
    assert "Complete Math Assignment" in res1["text"]

    # 2. Attempt duplicate creation of same task
    res_dup = await execute_policy_gate_and_tools(model_output, 'test_user_a', 'ws_a_1', False)
    assert "Duplicate" in res_dup["policy_decision"]
    assert "already exists" in res_dup["text"]

    # 3. List tasks
    list_output = json.dumps({
        "action": {
            "tool": "list_tasks",
            "parameters": {"filter": "pending"}
        }
    })
    res_list = await execute_policy_gate_and_tools(list_output, 'test_user_a', 'ws_a_1', False)
    assert "Complete Math Assignment" in res_list["text"]

    # 4. Complete task
    comp_output = json.dumps({
        "action": {
            "tool": "complete_task",
            "parameters": {"title_search": "Math Assignment"}
        }
    })
    res_comp = await execute_policy_gate_and_tools(comp_output, 'test_user_a', 'ws_a_1', False)
    assert "marked as completed" in res_comp["text"]

    # Verify completed in DB
    with get_db() as conn:
        row = conn.execute("SELECT completed FROM user_tasks WHERE user_id = 'test_user_a' AND title = 'Complete Math Assignment'").fetchone()
        assert row is not None and row["completed"] == 1

    # 5. Reopen task
    reopen_output = json.dumps({
        "action": {
            "tool": "reopen_task",
            "parameters": {"title_search": "Math Assignment"}
        }
    })
    res_reopen = await execute_policy_gate_and_tools(reopen_output, 'test_user_a', 'ws_a_1', False)
    assert "reopened" in res_reopen["text"]

    with get_db() as conn:
        row = conn.execute("SELECT completed FROM user_tasks WHERE user_id = 'test_user_a' AND title = 'Complete Math Assignment'").fetchone()
        assert row is not None and row["completed"] == 0
    print("PASS: test_tasks_lifecycle_and_deduplication")

async def test_calendar_conflict_detection_and_refusal_async():
    setup_test_data()
    # 1. Schedule Event 1 (Physics Lecture from 17:00 to 18:00)
    evt1_output = json.dumps({
        "action": {
            "tool": "schedule_event",
            "parameters": {
                "title": "Physics Lecture",
                "event_date": "2026-12-01",
                "start_time": "17:00",
                "end_time": "18:00"
            }
        }
    })
    res1 = await execute_policy_gate_and_tools(evt1_output, 'test_user_a', 'ws_a_1', False)
    assert res1["tool_executed"] == "schedule_event"
    assert "scheduled successfully" in res1["text"]

    # 2. Attempt Overlapping Event (Study Session from 17:30 to 19:00 on same date)
    evt_conflict = json.dumps({
        "action": {
            "tool": "schedule_event",
            "parameters": {
                "title": "Conflicting Study Session",
                "event_date": "2026-12-01",
                "start_time": "17:30",
                "end_time": "19:00"
            }
        }
    })
    res_conf = await execute_policy_gate_and_tools(evt_conflict, 'test_user_a', 'ws_a_1', False)
    # MUST REFUSE: never silently overwrite or schedule over!
    assert "Conflict Detected" in res_conf["policy_decision"]
    assert "Physics Lecture" in res_conf["text"]
    assert "No event was created" in res_conf["text"]

    # Verify database has exactly 1 event
    with get_db() as conn:
        evts = conn.execute("SELECT * FROM user_calendar_events WHERE user_id = 'test_user_a' AND event_date = '2026-12-01'").fetchall()
        assert len(evts) == 1
        assert evts[0]["title"] == "Physics Lecture"

    # 3. Schedule Non-overlapping event (19:30 to 20:30)
    evt_non_conflict = json.dumps({
        "action": {
            "tool": "schedule_event",
            "parameters": {
                "title": "Evening Revision",
                "event_date": "2026-12-01",
                "start_time": "19:30",
                "end_time": "20:30"
            }
        }
    })
    res_free = await execute_policy_gate_and_tools(evt_non_conflict, 'test_user_a', 'ws_a_1', False)
    assert "scheduled successfully" in res_free["text"]

    with get_db() as conn:
        evts = conn.execute("SELECT * FROM user_calendar_events WHERE user_id = 'test_user_a' AND event_date = '2026-12-01'").fetchall()
        assert len(evts) == 2
    print("PASS: test_calendar_conflict_detection_and_refusal")

async def test_youtube_notes_mandatory_no_transcript_rule_async():
    setup_test_data()
    # 1. Valid YouTube URL without transcript -> MUST STOP and return required notice
    yt_output = json.dumps({
        "action": {
            "tool": "process_youtube_notes",
            "parameters": {
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            }
        }
    })
    res_no_tr = await execute_policy_gate_and_tools(yt_output, 'test_user_a', 'ws_a_1', False)
    assert "No Transcript Available" in res_no_tr["policy_decision"]
    assert "No transcript available. No notes were created." in res_no_tr["text"]
    assert "paste the lecture transcript here" in res_no_tr["text"]

    # 2. Invalid YouTube URL
    yt_bad_url = json.dumps({
        "action": {
            "tool": "process_youtube_notes",
            "parameters": {
                "url": "https://example.com/not-youtube"
            }
        }
    })
    res_bad = await execute_policy_gate_and_tools(yt_bad_url, 'test_user_a', 'ws_a_1', False)
    assert "not a valid YouTube" in res_bad["text"]

    # 3. Manual transcript parsing with timestamps
    sample_transcript = """
    00:15 Introduction to Database Normalization
    First normal form requires atomic values and unique records.
    04:30 Second Normal Form and Partial Dependencies
    In 2NF every non-prime attribute must depend on the whole candidate key.
    08:45 Third Normal Form and Transitive Dependencies
    3NF eliminates transitive dependencies.
    """
    yt_manual = json.dumps({
        "action": {
            "tool": "process_youtube_notes",
            "parameters": {
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "manual_transcript": sample_transcript
            }
        }
    })
    res_manual = await execute_policy_gate_and_tools(yt_manual, 'test_user_a', 'ws_a_1', False)
    assert "Allowed & Executed" in res_manual["policy_decision"]
    assert "00:15" in res_manual["text"]
    assert "04:30" in res_manual["text"]
    assert "08:45" in res_manual["text"]

    # Verify saved to user_workspace_notes
    with get_db() as conn:
        notes = conn.execute("SELECT * FROM user_workspace_notes WHERE user_id = 'test_user_a' AND title LIKE 'Lecture Notes%'").fetchall()
        assert len(notes) >= 1
    print("PASS: test_youtube_notes_mandatory_no_transcript_rule")

async def test_exam_study_revision_plan_and_quiz_async():
    setup_test_data()
    # 1. When workspace has NO study materials -> Must report clearly
    plan_empty = json.dumps({
        "action": {
            "tool": "create_revision_plan",
            "parameters": {"exam_date": "2026-12-15"}
        }
    })
    res_empty = await execute_policy_gate_and_tools(plan_empty, 'test_user_a', 'ws_a_2', False)
    assert "couldn't find any uploaded study materials" in res_empty["text"]

    # 2. Add study material to workspace ws_a_2
    with get_db() as conn:
        conn.execute("""
            INSERT INTO user_workspace_notes (id, workspace_id, user_id, title, content, created_at, updated_at)
            VALUES ('note_study', 'ws_a_2', 'test_user_a', 'Data Structures Notes', 
            'Topic: Binary Search Trees\nBinary search trees maintain sorted keys for O(log n) lookup.\n\nTopic: Hash Tables\nHash tables use hash functions to achieve average O(1) time complexity.',
            ?, ?)
        """, (datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()))
        conn.commit()

    # 3. Create revision plan
    res_plan = await execute_policy_gate_and_tools(plan_empty, 'test_user_a', 'ws_a_2', False)
    assert "Exam Revision Plan" in res_plan["text"]
    assert "Binary Search Trees" in res_plan["text"] or "Hash Tables" in res_plan["text"]

    # 4. Generate quiz questions strictly grounded in notes
    quiz_output = json.dumps({
        "action": {
            "tool": "generate_quiz_questions",
            "parameters": {}
        }
    })
    res_quiz = await execute_policy_gate_and_tools(quiz_output, 'test_user_a', 'ws_a_2', False)
    assert "Practice Questions Grounded in Your Notes" in res_quiz["text"]
    assert "Question 1" in res_quiz["text"]

    # 5. Convert plan to tasks
    conv_output = json.dumps({
        "action": {
            "tool": "convert_plan_to_tasks",
            "parameters": {}
        }
    })
    res_conv = await execute_policy_gate_and_tools(conv_output, 'test_user_a', 'ws_a_2', False)
    assert "Created Revision Tasks" in res_conv["text"]

    # 6. Re-run convert plan to tasks -> MUST PREVENT DUPLICATES
    res_conv2 = await execute_policy_gate_and_tools(conv_output, 'test_user_a', 'ws_a_2', False)
    assert "already exist as tasks" in res_conv2["text"]
    print("PASS: test_exam_study_revision_plan_and_quiz")

async def main():
    test_context_isolation()
    test_database_multi_user_isolation()
    await test_policy_gate_kill_switch_async()
    await test_policy_gate_approval_staging_async()
    await test_tasks_lifecycle_and_deduplication_async()
    await test_calendar_conflict_detection_and_refusal_async()
    await test_youtube_notes_mandatory_no_transcript_rule_async()
    await test_exam_study_revision_plan_and_quiz_async()

    # FastApi TestClient roundtrip testing
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.security import generate_session_id, get_session_expiry

    session_id = generate_session_id()
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO sessions (session_id, user_id, expires_at, created_at) VALUES (?, 'test_user_a', ?, ?)",
                     (session_id, get_session_expiry(1), datetime.now(timezone.utc).isoformat()))
        conn.commit()

    client = TestClient(app, cookies={"session_id": session_id})

    # Test Calendar API
    res_cal = client.post("/api/user/calendar/events", json={
        "title": "System Test Meeting",
        "event_date": "2026-12-20",
        "start_time": "10:00",
        "end_time": "11:00",
        "category": "Work"
    })
    assert res_cal.status_code == 200
    evt_data = res_cal.json()
    evt_id = evt_data["event"]["id"]

    # Conflict check via API
    res_cal_dup = client.post("/api/user/calendar/events", json={
        "title": "Clashing Meeting",
        "event_date": "2026-12-20",
        "start_time": "10:30",
        "end_time": "11:30"
    })
    assert res_cal_dup.status_code == 409, "Should return 409 Conflict"

    # Fetch Calendar Events via API
    res_list_cal = client.get("/api/user/calendar/events?date=2026-12-20")
    assert res_list_cal.status_code == 200
    assert len(res_list_cal.json()["events"]) == 1

    # Delete Event
    res_del_cal = client.delete(f"/api/user/calendar/events/{evt_id}")
    assert res_del_cal.status_code == 200

    # User data includes calendar_events
    res_user_data = client.get("/api/user/data")
    assert res_user_data.status_code == 200
    assert "calendar_events" in res_user_data.json()

    print("PASS: test_api_endpoints_roundtrip")

    print("\n==================================================================")
    print("ALL 9 CORE AUTOMATED TEST SUITES PASSED SUCCESSFULLY WITH 0 ERRORS!")
    print("==================================================================\n")

if __name__ == '__main__':
    asyncio.run(main())
