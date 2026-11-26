import httpx
import sqlite3
from pathlib import Path
from backend.database import get_db, init_db
from backend.security import generate_session_id, get_session_expiry

init_db()

def test_multi_user_isolation():
    conn = get_db()
    cursor = conn.cursor()

    # Create User A
    cursor.execute("""
        INSERT INTO users (id, email, name, picture, created_at)
        VALUES ('usr_user_a', 'alice@test.local', 'Alice Tester', '', '2026-11-27T00:00:00Z')
        ON CONFLICT(id) DO UPDATE SET email = excluded.email
    """)
    session_a = generate_session_id()
    cursor.execute("""
        INSERT INTO sessions (session_id, user_id, expires_at, created_at)
        VALUES (?, 'usr_user_a', ?, '2026-11-27T00:00:00Z')
    """, (session_a, get_session_expiry(7)))

    # Create User B
    cursor.execute("""
        INSERT INTO users (id, email, name, picture, created_at)
        VALUES ('usr_user_b', 'bob@test.local', 'Bob Tester', '', '2026-11-27T00:00:00Z')
        ON CONFLICT(id) DO UPDATE SET email = excluded.email
    """)
    session_b = generate_session_id()
    cursor.execute("""
        INSERT INTO sessions (session_id, user_id, expires_at, created_at)
        VALUES (?, 'usr_user_b', ?, '2026-11-27T00:00:00Z')
    """, (session_b, get_session_expiry(7)))

    # Alice creates a task
    cursor.execute("""
        INSERT INTO user_tasks (id, user_id, title, source, due_date, priority, completed, workspace, created_at)
        VALUES ('tsk_alice_1', 'usr_user_a', 'Alice Secret Strategy Document', 'Email', 'Tomorrow', 'high', 0, 'Research', '2026-11-27T00:00:00Z')
    """)

    conn.commit()
    conn.close()

    # Test via API with Alice's session
    headers_a = {"Cookie": f"session_id={session_a}"}
    headers_b = {"Cookie": f"session_id={session_b}"}

    client = httpx.Client(base_url="http://127.0.0.1:8001")

    # Alice checks her tasks
    res_a = client.get("/api/user/data", headers=headers_a)
    data_a = res_a.json()
    alice_titles = [t["title"] for t in data_a["tasks"]]
    assert "Alice Secret Strategy Document" in alice_titles, "Alice should see her task"
    print("✓ Alice correctly sees her own task")

    # Bob checks his tasks
    res_b = client.get("/api/user/data", headers=headers_b)
    data_b = res_b.json()
    bob_titles = [t["title"] for t in data_b["tasks"]]
    assert "Alice Secret Strategy Document" not in bob_titles, "Bob must NOT see Alice's task"
    assert len(bob_titles) == 0, "Bob should have 0 tasks"
    print("✓ Bob has 0 tasks and CANNOT see Alice's data (Multi-user isolation verified)")

    # Test Gmail endpoint when not connected
    res_gmail = client.get("/api/gmail/messages", headers=headers_a)
    gmail_data = res_gmail.json()
    assert gmail_data["connected"] == False, "Gmail must be reported as not connected"
    assert len(gmail_data["messages"]) == 0, "Messages must be empty list, zero fake data"
    print("✓ Gmail endpoint correctly returns connected=False and empty messages (No fake data)")

    # Clean up test rows
    conn = get_db()
    conn.execute("DELETE FROM user_tasks WHERE id = 'tsk_alice_1'")
    conn.execute("DELETE FROM sessions WHERE session_id IN (?, ?)", (session_a, session_b))
    conn.execute("DELETE FROM users WHERE id IN ('usr_user_a', 'usr_user_b')")
    conn.commit()
    conn.close()

    print("All backend security and isolation tests passed successfully!")

if __name__ == "__main__":
    test_multi_user_isolation()
