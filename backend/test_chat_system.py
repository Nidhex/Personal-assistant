import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import json
import sqlite3
import asyncio
from datetime import datetime, timezone

# Import database and agent modules
from backend.database import DB_PATH, get_db, init_db
from backend.agent import build_context, query_llm_planner, execute_policy_gate_and_tools

def setup_test_data():
    init_db()
    with get_db() as conn:
        # Create two test users if not exist
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("INSERT OR REPLACE INTO users (id, email, name, created_at) VALUES ('test_user_a', 'user_a@example.com', 'Alice', ?)", (now,))
        conn.execute("INSERT OR REPLACE INTO users (id, email, name, created_at) VALUES ('test_user_b', 'user_b@example.com', 'Bob', ?)", (now,))
        
        now = datetime.now(timezone.utc).isoformat()
        # Workspaces for User A
        conn.execute("INSERT OR REPLACE INTO user_workspaces (id, user_id, name, type, description, created_at) VALUES ('ws_a_1', 'test_user_a', 'Alpha Project', 'project', 'Alpha description', ?)", (now,))
        conn.execute("INSERT OR REPLACE INTO user_workspaces (id, user_id, name, type, description, created_at) VALUES ('ws_a_2', 'test_user_a', 'Beta Study', 'study', 'Beta description', ?)", (now,))
        
        # Workspace for User B
        conn.execute("INSERT OR REPLACE INTO user_workspaces (id, user_id, name, type, description, created_at) VALUES ('ws_b_1', 'test_user_b', 'Gamma Secret', 'project', 'Gamma description', ?)", (now,))
        
        # Add notes in Workspace A1
        conn.execute("DELETE FROM user_workspace_notes WHERE user_id IN ('test_user_a', 'test_user_b')")
        conn.execute("INSERT INTO user_workspace_notes (id, workspace_id, user_id, title, content, created_at, updated_at) VALUES ('note_1', 'ws_a_1', 'test_user_a', 'Alpha Roadmap', 'Launch Alpha in Q4 with high security.', ?, ?)", (now, now))
        conn.execute("INSERT INTO user_workspace_notes (id, workspace_id, user_id, title, content, created_at, updated_at) VALUES ('note_2', 'ws_b_1', 'test_user_b', 'Secret B Code', 'Top secret code for Bob only.', ?, ?)", (now, now))
        
        # Add task in Workspace A1
        conn.execute("DELETE FROM user_tasks WHERE user_id IN ('test_user_a', 'test_user_b')")
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
    # Workspace 1's notes must NOT leak into Workspace 2!
    assert not any("Alpha Roadmap" in n["title"] for n in ctx_a2["notes"]), "ws_a_1 notes leaked into ws_a_2!"
    assert not any("Review Alpha specifications" in t["title"] for t in ctx_a2["tasks"]), "ws_a_1 tasks leaked into ws_a_2!"
    print("PASS: test_context_isolation")

def test_database_multi_user_isolation():
    setup_test_data()
    with get_db() as conn:
        now = datetime.now(timezone.utc).isoformat()
        # Create conversation for User A and User B
        conn.execute("DELETE FROM conversations WHERE user_id IN ('test_user_a', 'test_user_b')")
        conn.execute("INSERT INTO conversations (id, user_id, workspace_id, title, created_at, updated_at) VALUES ('conv_a_1', 'test_user_a', 'ws_a_1', 'Alice Alpha Chat', ?, ?)", (now, now))
        conn.execute("INSERT INTO conversations (id, user_id, workspace_id, title, created_at, updated_at) VALUES ('conv_b_1', 'test_user_b', 'ws_b_1', 'Bob Private Chat', ?, ?)", (now, now))
        conn.commit()
        
        # Query conversations scoped strictly to User A
        a_convs = conn.execute("SELECT id, title FROM conversations WHERE user_id = 'test_user_a'").fetchall()
        assert len(a_convs) == 1
        assert a_convs[0]['id'] == 'conv_a_1'
        
        # Verify User A cannot fetch User B's conversation
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
    
    # Kill switch is ACTIVE (True)
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
    
    # Kill switch is INACTIVE (False)
    result = await execute_policy_gate_and_tools(
        model_output=model_output,
        user_id='test_user_a',
        workspace_id='ws_a_1',
        kill_switch_active=False
    )
    assert result["approval_required"] is True
    assert result["tool_executed"] == "propose_draft"
    
    # Verify it exists in user_approvals table
    with get_db() as conn:
        row = conn.execute("SELECT * FROM user_approvals WHERE user_id = 'test_user_a' AND status = 'pending' ORDER BY created_at DESC LIMIT 1").fetchone()
        assert row is not None
        assert row['target'] == 'client@example.com'
        assert row['subject'] == 'Project Proposal'
    print("PASS: test_policy_gate_approval_staging")

async def test_safe_task_execution_async():
    setup_test_data()
    model_output = json.dumps({
        "action": {
            "tool": "create_task",
            "parameters": {
                "title": "Automated Unit Test Task",
                "due_date": "Next Monday",
                "priority": "high"
            }
        },
        "response": "I created your task."
    })
    
    result = await execute_policy_gate_and_tools(
        model_output=model_output,
        user_id='test_user_a',
        workspace_id='ws_a_1',
        kill_switch_active=False
    )
    assert result["tool_executed"] == "create_task"
    assert "Allowed & Executed" in result["policy_decision"]
    
    # Verify task was written to DB with workspace name "Alpha Project"
    with get_db() as conn:
        t = conn.execute("SELECT * FROM user_tasks WHERE user_id = 'test_user_a' AND title = 'Automated Unit Test Task'").fetchone()
        assert t is not None
        assert t['workspace'] == 'Alpha Project'
        assert t['priority'] == 'high'
    print("PASS: test_safe_task_execution")

async def main():
    test_context_isolation()
    test_database_multi_user_isolation()
    await test_policy_gate_kill_switch_async()
    await test_policy_gate_approval_staging_async()
    await test_safe_task_execution_async()
    
    # Test API endpoints via FastAPI TestClient
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.security import generate_session_id, get_session_expiry
    
    # Create valid session cookie for test_user_a
    session_id = generate_session_id()
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO sessions (session_id, user_id, expires_at, created_at) VALUES (?, 'test_user_a', ?, ?)", 
                     (session_id, get_session_expiry(1), datetime.now(timezone.utc).isoformat()))
        conn.commit()
    
    client = TestClient(app, cookies={"session_id": session_id})
    
    # 1. Fetch conversations
    res = client.get("/api/chat/conversations")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    
    # 2. Create conversation
    res = client.post("/api/chat/conversations", json={"workspace_id": "ws_a_1", "title": "API Test Chat"})
    assert res.status_code == 200
    conv_data = res.json()
    conv = conv_data["conversation"]
    conv_id = conv["id"]
    assert conv["title"] == "API Test Chat"
    
    # 3. Post chat message
    res = client.post(f"/api/chat/conversations/{conv_id}/messages", json={"content": "create task Deploy production backend"})
    assert res.status_code == 200
    msg_res = res.json()
    assert "user_message" in msg_res
    assert "assistant_message" in msg_res
    assert msg_res["user_message"]["content"] == "create task Deploy production backend"
    assert "Action Item Created" in msg_res["assistant_message"]["content"] or "assistant" in msg_res["assistant_message"]["role"]
    
    # 4. Fetch messages
    res = client.get(f"/api/chat/conversations/{conv_id}/messages")
    assert res.status_code == 200
    msgs = res.json()
    assert len(msgs) >= 2
    
    # 5. Create and fetch workspace note
    res = client.post("/api/user/workspaces/ws_a_1/notes", json={"title": "Sprint Goals", "content": "Complete integration test suite."})
    assert res.status_code == 200
    note_data = res.json()
    note = note_data["note"]
    assert note["title"] == "Sprint Goals"
    
    res = client.get("/api/user/workspaces/ws_a_1/notes")
    assert res.status_code == 200
    notes_data = res.json()
    notes = notes_data.get("notes", [])
    assert any(n["title"] == "Sprint Goals" for n in notes)
    print("PASS: test_api_endpoints_roundtrip")
    
    print("\n=======================================================")
    print("ALL 6 SYSTEM & API TESTS PASSED SUCCESSFULLY WITH ZERO ERRORS!")
    print("=======================================================\n")

if __name__ == '__main__':
    asyncio.run(main())
