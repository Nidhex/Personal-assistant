import asyncio
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from backend.agent import execute_policy_gate_and_tools
from backend.database import get_db, init_db
from backend.main import app, get_current_user
from backend.security import generate_session_id, get_session_expiry


def _setup_user(user_id: str, email: str, gmail_connected: int = 1):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_tasks WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM user_approvals WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM user_activity WHERE user_id = ?", (user_id,))
    cursor.execute(
        """
        INSERT OR REPLACE INTO users (id, email, name, created_at)
        VALUES (?, ?, ?, datetime('now'))
        """,
        (user_id, email, f"User {user_id}"),
    )
    conn.commit()
    conn.close()


def _client_for(user_id: str) -> TestClient:
    sid = generate_session_id()
    conn = get_db()
    conn.execute(
        "INSERT INTO sessions (session_id, user_id, expires_at, created_at) VALUES (?, ?, ?, datetime('now'))",
        (sid, user_id, get_session_expiry()),
    )
    conn.commit()
    conn.close()
    client = TestClient(app)
    client.cookies.set("session_id", sid)
    return client


def test_propose_from_email_and_approve():
    init_db()
    uid = "test_prop_user_1"
    _setup_user(uid, "prop1@example.com")
    client = _client_for(uid)

    fake_detail = {
        "id": "msg_101",
        "subject": "Quarterly Report Due",
        "senderName": "Alice",
        "from": "alice@example.com",
        "snippet": "Please submit the quarterly report by Friday.",
    }

    app.dependency_overrides[get_current_user] = lambda: {"id": uid, "email": "prop1@example.com", "gmail_connected": True}
    with patch("backend.main.fetch_gmail_message_detail", new=AsyncMock(return_value=fake_detail)):
        res = client.post("/api/gmail/messages/msg_101/propose-task")
    app.dependency_overrides.clear()
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "pending"
    assert data["approval_id"].startswith("appr_")

    conn = get_db()
    approvals = conn.execute("SELECT * FROM user_approvals WHERE user_id = ?", (uid,)).fetchall()
    tasks = conn.execute("SELECT * FROM user_tasks WHERE user_id = ?", (uid,)).fetchall()
    conn.close()
    assert len(approvals) == 1
    assert approvals[0]["type"] == "Task Proposal"
    assert approvals[0]["status"] == "pending"
    assert len(tasks) == 0

    # Approve it
    appr_id = data["approval_id"]
    res2 = client.post(f"/api/user/approvals/{appr_id}/action", json={"action": "approve"})
    assert res2.status_code == 200
    assert res2.json()["status"] == "approved"

    conn = get_db()
    tasks = conn.execute("SELECT * FROM user_tasks WHERE user_id = ?", (uid,)).fetchall()
    acts = conn.execute(
        "SELECT * FROM user_activity WHERE user_id = ? AND result = 'Approval completed: task created'",
        (uid,),
    ).fetchall()
    conn.close()
    assert len(tasks) == 1
    assert tasks[0]["source"] == "Agent Proposal"
    assert tasks[0]["source_email_id"] == "msg_101"
    assert len(acts) == 1
    print("PASS: test_propose_from_email_and_approve")


def test_concurrent_and_retry_approvals():
    init_db()
    uid = "test_prop_user_2"
    _setup_user(uid, "prop2@example.com")
    client = _client_for(uid)

    fake_detail = {
        "id": "msg_202",
        "subject": "Review PR",
        "senderName": "Bob",
        "from": "bob@example.com",
        "snippet": "Can you review PR #42?",
    }
    app.dependency_overrides[get_current_user] = lambda: {"id": uid, "email": "prop2@example.com", "gmail_connected": True}
    with patch("backend.main.fetch_gmail_message_detail", new=AsyncMock(return_value=fake_detail)):
        res = client.post("/api/gmail/messages/msg_202/propose-task")
    app.dependency_overrides.clear()
    appr_id = res.json()["approval_id"]

    def _approve():
        c = _client_for(uid)
        return c.post(f"/api/user/approvals/{appr_id}/action", json={"action": "approve"})

    with ThreadPoolExecutor(max_workers=2) as pool:
        r1, r2 = list(pool.map(lambda _: _approve(), range(2)))
    assert r1.status_code == 200
    assert r2.status_code == 200

    # Retry once more
    r3 = client.post(f"/api/user/approvals/{appr_id}/action", json={"action": "approve"})
    assert r3.status_code == 200

    conn = get_db()
    tasks = conn.execute("SELECT * FROM user_tasks WHERE user_id = ?", (uid,)).fetchall()
    conn.close()
    assert len(tasks) == 1
    print("PASS: test_concurrent_and_retry_approvals")


def test_reject_and_approve_after_reject_and_user_isolation():
    init_db()
    uid = "test_prop_user_3"
    other_uid = "test_prop_user_other"
    _setup_user(uid, "prop3@example.com")
    _setup_user(other_uid, "other@example.com")
    client = _client_for(uid)
    other_client = _client_for(other_uid)

    fake_detail = {
        "id": "msg_303",
        "subject": "Ignore me",
        "senderName": "Carol",
        "from": "carol@example.com",
        "snippet": "Optional reading.",
    }
    app.dependency_overrides[get_current_user] = lambda: {"id": uid, "email": "prop3@example.com", "gmail_connected": True}
    with patch("backend.main.fetch_gmail_message_detail", new=AsyncMock(return_value=fake_detail)):
        res = client.post("/api/gmail/messages/msg_303/propose-task")
    app.dependency_overrides.clear()
    appr_id = res.json()["approval_id"]

    # User isolation: other user cannot act on uid's approval
    iso_res = other_client.post(f"/api/user/approvals/{appr_id}/action", json={"action": "approve"})
    assert iso_res.status_code == 404

    # Reject
    rej = client.post(f"/api/user/approvals/{appr_id}/action", json={"action": "reject"})
    assert rej.status_code == 200
    assert rej.json()["status"] == "rejected"

    # Approve after reject -> still no task
    after = client.post(f"/api/user/approvals/{appr_id}/action", json={"action": "approve"})
    assert after.status_code == 200
    assert after.json()["status"] == "rejected"

    conn = get_db()
    tasks = conn.execute("SELECT * FROM user_tasks WHERE user_id = ?", (uid,)).fetchall()
    conn.close()
    assert len(tasks) == 0
    print("PASS: test_reject_and_approve_after_reject_and_user_isolation")


def test_server_side_bypass_refusal():
    init_db()
    uid = "test_prop_user_4"
    _setup_user(uid, "prop4@example.com")

    bypass_json = json.dumps({
        "response": "Creating task directly",
        "action": {
            "tool": "create_task",
            "parameters": {"title": "Bypassed Task", "due_date": "Today", "priority": "high"},
        },
    })
    res = asyncio.run(execute_policy_gate_and_tools(bypass_json, uid, None, False, email_derived=True))
    assert "Refused" in res["policy_decision"]

    conn = get_db()
    tasks = conn.execute("SELECT * FROM user_tasks WHERE user_id = ?", (uid,)).fetchall()
    approvals = conn.execute("SELECT * FROM user_approvals WHERE user_id = ?", (uid,)).fetchall()
    acts = conn.execute("SELECT * FROM user_activity WHERE user_id = ? AND status = 'Refused'", (uid,)).fetchall()
    conn.close()
    assert len(tasks) == 0
    assert len(approvals) == 0
    assert len(acts) == 1
    print("PASS: test_server_side_bypass_refusal")


def test_regression_chat_create_task_and_email_draft():
    init_db()
    uid = "test_prop_user_5"
    _setup_user(uid, "prop5@example.com")
    client = _client_for(uid)

    chat_json = json.dumps({
        "response": "Creating chat task",
        "action": {
            "tool": "create_task",
            "parameters": {"title": "Direct Chat Task", "due_date": "Today", "priority": "normal"},
        },
    })
    res = asyncio.run(execute_policy_gate_and_tools(chat_json, uid, None, False, email_derived=False))
    assert res["tool_executed"] == "create_task"

    draft_json = json.dumps({
        "response": "Drafting email",
        "action": {
            "tool": "propose_draft",
            "parameters": {"target": "x@example.com", "subject": "Hi", "draft_content": "Hello"},
        },
    })
    d_res = asyncio.run(execute_policy_gate_and_tools(draft_json, uid, None, False, email_derived=False))
    assert d_res["approval_required"] is True
    draft_appr_id = d_res["approval_id"]

    appr_res = client.post(f"/api/user/approvals/{draft_appr_id}/action", json={"action": "approve"})
    assert appr_res.status_code == 200
    assert appr_res.json()["status"] == "approved"

    conn = get_db()
    tasks = conn.execute("SELECT * FROM user_tasks WHERE user_id = ?", (uid,)).fetchall()
    conn.close()
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Direct Chat Task"
    print("PASS: test_regression_chat_create_task_and_email_draft")


def test_extract_email_tasks_queues_proposals_and_dedupes():
    init_db()
    uid = "test_prop_user_6"
    other_uid = "test_prop_user_6_other"
    _setup_user(uid, "prop6@example.com")
    _setup_user(other_uid, "prop6_other@example.com")
    client = _client_for(uid)
    other_client = _client_for(other_uid)

    fake_messages = {
        "messages": [
            {
                "id": "msg_ext_1",
                "subject": "Assignment 3 Deadline",
                "snippet": "Please submit Assignment 3 by tomorrow.",
                "senderName": "Prof. Smith",
            },
            {
                "id": "msg_ext_2",
                "subject": "Weekly Newsletter",
                "snippet": "Just some reading material.",
                "senderName": "News",
            },
        ]
    }

    extract_json = json.dumps({
        "response": "Scanning emails for deadlines",
        "action": {"tool": "extract_email_tasks", "parameters": {"max_results": 10}},
    })

    with patch("backend.agent.fetch_gmail_messages", new=AsyncMock(return_value=fake_messages)):
        res1 = asyncio.run(execute_policy_gate_and_tools(extract_json, uid, None, False, email_derived=False))
        # Retry should dedupe against pending proposals
        res2 = asyncio.run(execute_policy_gate_and_tools(extract_json, uid, None, False, email_derived=False))

    assert res1["tool_executed"] == "extract_email_tasks"
    assert res1["approval_required"] is True
    assert res2["approval_required"] is False

    conn = get_db()
    tasks_before = conn.execute("SELECT * FROM user_tasks WHERE user_id = ?", (uid,)).fetchall()
    approvals = conn.execute(
        "SELECT * FROM user_approvals WHERE user_id = ? AND type = 'Task Proposal' AND status = 'pending'",
        (uid,),
    ).fetchall()
    other_approvals = conn.execute(
        "SELECT * FROM user_approvals WHERE user_id = ?",
        (other_uid,),
    ).fetchall()
    conn.close()

    assert len(tasks_before) == 0
    assert len(approvals) == 1
    assert len(other_approvals) == 0
    payload = json.loads(approvals[0]["draft_content"])
    assert payload["source_email_id"] == "msg_ext_1"
    assert payload["priority"] == "high"
    assert payload["workspace"] == "General"

    appr_id = approvals[0]["id"]
    # Other user cannot approve
    assert other_client.post(f"/api/user/approvals/{appr_id}/action", json={"action": "approve"}).status_code == 404

    # Approve once, then retry -> still 1 task
    assert client.post(f"/api/user/approvals/{appr_id}/action", json={"action": "approve"}).status_code == 200
    assert client.post(f"/api/user/approvals/{appr_id}/action", json={"action": "approve"}).status_code == 200

    conn = get_db()
    tasks_after = conn.execute("SELECT * FROM user_tasks WHERE user_id = ?", (uid,)).fetchall()
    conn.close()
    assert len(tasks_after) == 1
    assert tasks_after[0]["source"] == "Agent Proposal"
    assert tasks_after[0]["source_email_id"] == "msg_ext_1"
    print("PASS: test_extract_email_tasks_queues_proposals_and_dedupes")


if __name__ == "__main__":
    test_propose_from_email_and_approve()
    test_concurrent_and_retry_approvals()
    test_reject_and_approve_after_reject_and_user_isolation()
    test_server_side_bypass_refusal()
    test_regression_chat_create_task_and_email_draft()
    test_extract_email_tasks_queues_proposals_and_dedupes()
    print("\nALL TASK PROPOSAL TESTS PASSED!")
