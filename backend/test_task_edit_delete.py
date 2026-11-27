import os
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from backend.database import get_db, init_db
from backend.main import app, get_current_user
from backend.security import generate_session_id, get_session_expiry


def _setup_user(user_id: str, email: str):
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


def _create_task(client: TestClient, title="Original Title", due_date="Today", priority="normal", workspace="General"):
    res = client.post(
        "/api/user/tasks",
        json={
            "title": title,
            "source": "User Created",
            "due_date": due_date,
            "priority": priority,
            "workspace": workspace,
        },
    )
    assert res.status_code == 200, res.text
    return res.json()["id"]


def test_edit_title_due_date_priority_preserves_other_columns():
    init_db()
    uid = "test_edit_user_1"
    _setup_user(uid, "edit1@example.com")
    client = _client_for(uid)
    task_id = _create_task(client, title="Initial Task", due_date="Today", priority="normal", workspace="Research")

    conn = get_db()
    before = dict(conn.execute("SELECT * FROM user_tasks WHERE id = ?", (task_id,)).fetchone())
    conn.close()

    res = client.patch(
        f"/api/user/tasks/{task_id}",
        json={"title": "  Updated Task  ", "due_date": "Tomorrow", "priority": "high"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["title"] == "Updated Task"
    assert data["due_date"] == "Tomorrow"
    assert data["priority"] == "high"
    assert data["source"] == before["source"]
    assert data["source_email_id"] == before["source_email_id"]
    assert data["workspace"] == before["workspace"]
    assert data["completed"] == before["completed"]
    assert data["created_at"] == before["created_at"]

    conn = get_db()
    acts = conn.execute(
        "SELECT * FROM user_activity WHERE user_id = ? AND trigger = 'Task edited'",
        (uid,),
    ).fetchall()
    conn.close()
    assert len(acts) == 1
    assert "Updated Task" in acts[0]["result"]
    print("PASS: test_edit_title_due_date_priority_preserves_other_columns")


def test_edit_validation_400_cases():
    init_db()
    uid = "test_edit_user_2"
    _setup_user(uid, "edit2@example.com")
    client = _client_for(uid)
    task_id = _create_task(client, title="Valid Task")

    for bad_body in [
        {},
        {"title": "   "},
        {"title": "x" * 201},
        {"priority": "urgent"},
    ]:
        res = client.patch(f"/api/user/tasks/{task_id}", json=bad_body)
        assert res.status_code == 400, f"Expected 400 for {bad_body}, got {res.status_code}"

    conn = get_db()
    row = conn.execute("SELECT title, priority FROM user_tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    assert row["title"] == "Valid Task"
    assert row["priority"] == "normal"
    print("PASS: test_edit_validation_400_cases")


def test_user_isolation_edit_and_delete():
    init_db()
    uid_a = "test_edit_user_a"
    uid_b = "test_edit_user_b"
    _setup_user(uid_a, "edita@example.com")
    _setup_user(uid_b, "editb@example.com")
    client_a = _client_for(uid_a)
    client_b = _client_for(uid_b)

    task_id = _create_task(client_a, title="User A Task")

    res_edit = client_b.patch(f"/api/user/tasks/{task_id}", json={"title": "Hacked"})
    assert res_edit.status_code == 404
    assert res_edit.json()["detail"] == "Task not found."

    res_del = client_b.delete(f"/api/user/tasks/{task_id}")
    assert res_del.status_code == 404
    assert res_del.json()["detail"] == "Task not found."

    conn = get_db()
    row = conn.execute("SELECT title FROM user_tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    assert row is not None and row["title"] == "User A Task"
    print("PASS: test_user_isolation_edit_and_delete")


def test_delete_removes_task_and_logs_activity():
    init_db()
    uid = "test_edit_user_3"
    _setup_user(uid, "edit3@example.com")
    client = _client_for(uid)
    task_id = _create_task(client, title="Task To Delete")

    res_del = client.delete(f"/api/user/tasks/{task_id}")
    assert res_del.status_code == 200
    assert res_del.json() == {"success": True}

    data_res = client.get("/api/user/data")
    assert data_res.status_code == 200
    ids = [t["id"] for t in data_res.json()["tasks"]]
    assert task_id not in ids

    res_del_again = client.delete(f"/api/user/tasks/{task_id}")
    assert res_del_again.status_code == 404

    conn = get_db()
    acts = conn.execute(
        "SELECT * FROM user_activity WHERE user_id = ? AND trigger = 'Task deleted'",
        (uid,),
    ).fetchall()
    conn.close()
    assert len(acts) == 1
    assert "Task To Delete" in acts[0]["result"]
    print("PASS: test_delete_removes_task_and_logs_activity")


def test_email_approved_task_edit_and_delete():
    init_db()
    uid = "test_edit_user_4"
    _setup_user(uid, "edit4@example.com")
    client = _client_for(uid)

    fake_detail = {
        "id": "msg_edit_404",
        "subject": "Email Proposal Subject",
        "senderName": "Sender",
        "from": "sender@example.com",
        "snippet": "Please handle this.",
    }
    app.dependency_overrides[get_current_user] = lambda: {"id": uid, "email": "edit4@example.com", "gmail_connected": True}
    with patch("backend.main.fetch_gmail_message_detail", new=AsyncMock(return_value=fake_detail)):
        prop_res = client.post("/api/gmail/messages/msg_edit_404/propose-task")
    app.dependency_overrides.clear()
    appr_id = prop_res.json()["approval_id"]

    appr_res = client.post(f"/api/user/approvals/{appr_id}/action", json={"action": "approve"})
    assert appr_res.status_code == 200

    conn = get_db()
    task_row = conn.execute("SELECT * FROM user_tasks WHERE user_id = ?", (uid,)).fetchone()
    conn.close()
    assert task_row is not None
    task_id = task_row["id"]

    edit_res = client.patch(f"/api/user/tasks/{task_id}", json={"title": "Edited Email Task", "priority": "medium"})
    assert edit_res.status_code == 200
    edited = edit_res.json()
    assert edited["title"] == "Edited Email Task"
    assert edited["priority"] == "medium"
    assert edited["source_email_id"] == "msg_edit_404"
    assert edited["source"] == "Agent Proposal"

    del_res = client.delete(f"/api/user/tasks/{task_id}")
    assert del_res.status_code == 200
    print("PASS: test_email_approved_task_edit_and_delete")


if __name__ == "__main__":
    test_edit_title_due_date_priority_preserves_other_columns()
    test_edit_validation_400_cases()
    test_user_isolation_edit_and_delete()
    test_delete_removes_task_and_logs_activity()
    test_email_approved_task_edit_and_delete()
    print("\nALL TASK EDIT & DELETE TESTS PASSED!")
