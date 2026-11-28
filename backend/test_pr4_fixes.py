import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from backend.agent import retrieve_relevant_notes
from backend.database import get_db, init_db
from backend.main import app
from backend.security import generate_session_id, get_session_expiry


def _setup_user(user_id: str, email: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_tasks WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM user_approvals WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM user_workspace_notes WHERE user_id = ?", (user_id,))
    cursor.execute(
        "INSERT OR REPLACE INTO users (id, email, name, created_at) VALUES (?, ?, ?, datetime('now'))",
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


def test_question_result_endpoint():
    init_db()
    uid = "test_pr4_q_user"
    _setup_user(uid, "pr4q@example.com")
    client = _client_for(uid)

    r_ok = client.post("/api/study/question-result", json={"topic": "Binary Trees", "result": "correct"})
    assert r_ok.status_code == 200, r_ok.text
    assert r_ok.json()["requeued_task_id"] is None

    r_wrong = client.post("/api/study/question-result", json={"topic": "Graph BFS", "result": "wrong"})
    assert r_wrong.status_code == 200, r_wrong.text
    assert r_wrong.json()["requeued_task_id"] is not None

    conn = get_db()
    tasks = conn.execute("SELECT * FROM user_tasks WHERE user_id = ?", (uid,)).fetchall()
    conn.close()
    assert len(tasks) == 1
    assert "Graph BFS" in tasks[0]["title"]


def test_gmail_draft_uncertain_and_idempotent():
    init_db()
    uid = "test_pr4_draft_user"
    _setup_user(uid, "pr4draft@example.com")
    client = _client_for(uid)

    conn = get_db()
    conn.execute(
        """
        INSERT INTO user_approvals (id, user_id, type, target, subject, reason, risk_level, draft_content, status, created_at)
        VALUES ('appr_uncertain_1', ?, 'Email Draft', 'a@b.com', 'Hello', 'Reason', 'Medium', 'Body', 'pending', datetime('now'))
        """,
        (uid,),
    )
    conn.commit()
    conn.close()

    # Uncertain outcome (empty id -> RuntimeError -> 502, gmail_draft_id stays 'creating')
    with patch("backend.google_service.create_gmail_draft", new=AsyncMock(side_effect=RuntimeError("UNCERTAIN_DRAFT_OUTCOME"))):
        res = client.post("/api/user/approvals/appr_uncertain_1/action", json={"action": "approve"})
    assert res.status_code == 502

    conn = get_db()
    row = conn.execute("SELECT status, gmail_draft_id FROM user_approvals WHERE id = 'appr_uncertain_1'").fetchone()
    conn.close()
    assert row["status"] == "approved"
    assert row["gmail_draft_id"] == "creating"


def test_semantic_search_fallback_and_planning():
    init_db()
    uid = "test_pr4_sem_user"
    _setup_user(uid, "pr4sem@example.com")
    client = _client_for(uid)

    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO user_workspaces (id, user_id, name, type, description, created_at) VALUES ('ws_sem_1', ?, 'Study', 'General', 'Desc', datetime('now'))",
        (uid,),
    )
    conn.execute(
        "INSERT INTO user_workspace_notes (id, workspace_id, user_id, title, content, created_at, updated_at) VALUES ('n1', 'ws_sem_1', ?, 'Relational Algebra', 'Joins and projections in SQL', datetime('now'), datetime('now'))",
        (uid,),
    )
    conn.execute(
        "INSERT INTO user_workspace_notes (id, workspace_id, user_id, title, content, created_at, updated_at) VALUES ('n2', 'ws_sem_1', ?, 'Sorting', 'Quick sort and merge sort', datetime('now'), datetime('now'))",
        (uid,),
    )
    conn.commit()
    conn.close()

    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        results = retrieve_relevant_notes(uid, "ws_sem_1", "SQL joins", top_k=1)
        assert len(results) == 1
        assert results[0]["title"] == "Relational Algebra"

        plan_res = client.post("/api/planning/generate", json={"goal": "Finish OS Lab", "target_date": "2026-12-05"})
        assert plan_res.status_code == 200
        assert len(plan_res.json()["milestones"]) >= 3
        assert "Finish OS Lab" in plan_res.json()["milestones"][0]["title"]
