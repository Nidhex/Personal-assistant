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


def test_reconcile_gmail_draft_on_retry_and_marker_discipline():
    init_db()
    uid = "test_pr4_rec_user"
    _setup_user(uid, "pr4rec@example.com")
    client = _client_for(uid)

    conn = get_db()
    conn.execute(
        """
        INSERT INTO user_approvals (id, user_id, type, target, subject, reason, risk_level, draft_content, status, gmail_draft_id, created_at)
        VALUES ('appr_rec_1', ?, 'Email Draft', 'a@b.com', 'Subj', 'Reason', 'Medium', 'Body', 'approved', 'creating', datetime('now'))
        """,
        (uid,),
    )
    conn.commit()
    conn.close()

    # 1. Ambiguity stays unknown when reconcile returns None -> 409, no new draft created
    with patch("backend.google_service.reconcile_gmail_draft", new=AsyncMock(return_value=None)):
        r_409 = client.post("/api/user/approvals/appr_rec_1/action", json={"action": "approve"})
    assert r_409.status_code == 409

    # 2. Reconciliation adopts matched draft ID -> 200 and stores gmail_draft_id
    with patch("backend.google_service.reconcile_gmail_draft", new=AsyncMock(return_value="draft_adopted_99")):
        r_ok = client.post("/api/user/approvals/appr_rec_1/action", json={"action": "approve"})
    assert r_ok.status_code == 200
    assert r_ok.json()["gmail_draft_id"] == "draft_adopted_99"

    # 3. Subsequent retry is idempotent (does not re-create)
    r_idem = client.post("/api/user/approvals/appr_rec_1/action", json={"action": "approve"})
    assert r_idem.status_code == 200
    assert r_idem.json()["gmail_draft_id"] == "draft_adopted_99"


def test_embeddings_stored_on_insert_and_chat_retrieval():
    init_db()
    uid = "test_pr4_emb_user"
    _setup_user(uid, "pr4emb@example.com")
    client = _client_for(uid)

    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO user_workspaces (id, user_id, name, type, description, created_at) VALUES ('ws_emb_1', ?, 'Study', 'General', 'Desc', datetime('now'))",
        (uid,),
    )
    conn.commit()
    conn.close()

    with patch("backend.agent.generate_embedding", return_value=[0.1, 0.2, 0.3]):
        res = client.post(
            "/api/user/workspaces/ws_emb_1/notes",
            json={"title": "OS Paging", "content": "Virtual memory page tables"},
        )
    assert res.status_code == 200, res.text

    conn = get_db()
    row = conn.execute("SELECT embedding FROM user_workspace_notes WHERE user_id = ? AND workspace_id = 'ws_emb_1'", (uid,)).fetchone()
    conn.close()
    assert row is not None and json.loads(row["embedding"]) == [0.1, 0.2, 0.3]

    # Chat path calls build_context -> retrieve_relevant_notes
    from backend.agent import build_context
    ctx = build_context(uid, workspace_id="ws_emb_1", query="page tables")
    assert len(ctx["notes"]) == 1
    assert ctx["notes"][0]["title"] == "OS Paging"


def test_mocked_gemini_planning():
    init_db()
    uid = "test_pr4_plan_user"
    _setup_user(uid, "pr4plan@example.com")
    client = _client_for(uid)

    mock_resp = MagicMock()
    mock_resp.text = json.dumps([
        {"id": "m1", "title": "Step 1", "due_date": "2026-12-01", "status": "in_progress"},
        {"id": "m2", "title": "Step 2", "due_date": "2026-12-03", "status": "pending"},
        {"id": "m3", "title": "Step 3", "due_date": "2026-12-05", "status": "pending"},
    ])
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_resp

    fake_genai = MagicMock()
    fake_genai.Client.return_value = mock_client
    fake_google = MagicMock()
    fake_google.genai = fake_genai
    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_key"}):
        with patch.dict(sys.modules, {"google": fake_google, "google.genai": fake_genai}):
            res = client.post("/api/planning/generate", json={"goal": "Launch App", "target_date": "2026-12-05"})
    assert res.status_code == 200
    assert len(res.json()["milestones"]) == 3
    assert res.json()["milestones"][0]["title"] == "Step 1"


def test_reconcile_marker_content_validation():
    import asyncio
    import base64
    from backend.google_service import reconcile_gmail_draft

    def _b64(s: str) -> str:
        return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii")

    def _mock_client(headers_list, body_text):
        list_resp = MagicMock(status_code=200)
        list_resp.json.return_value = {"drafts": [{"id": "d_match"}]}
        det_resp = MagicMock(status_code=200)
        det_resp.json.return_value = {
            "message": {
                "payload": {
                    "headers": headers_list,
                    "body": {"data": _b64(body_text)},
                }
            }
        }
        client_inst = AsyncMock()
        client_inst.get.side_effect = [list_resp, det_resp]
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=client_inst)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    with patch("backend.google_service.get_valid_access_token", new=AsyncMock(return_value="tok")):
        # 1. Exact marker + content match -> adopts
        with patch("httpx.AsyncClient", return_value=_mock_client([
            {"name": "X-Assistant-Approval-Id", "value": "appr_1"},
            {"name": "To", "value": "a@b.com"},
            {"name": "Subject", "value": "Subj"},
        ], "Body")):
            assert asyncio.run(reconcile_gmail_draft("u1", "appr_1", "a@b.com", "Subj", "Body")) == "d_match"

        # 2. Marker matches but body altered -> None
        with patch("httpx.AsyncClient", return_value=_mock_client([
            {"name": "X-Assistant-Approval-Id", "value": "appr_1"},
            {"name": "To", "value": "a@b.com"},
            {"name": "Subject", "value": "Subj"},
        ], "Altered Body")):
            assert asyncio.run(reconcile_gmail_draft("u1", "appr_1", "a@b.com", "Subj", "Body")) is None

        # 3. Marker matches but recipient altered -> None
        with patch("httpx.AsyncClient", return_value=_mock_client([
            {"name": "X-Assistant-Approval-Id", "value": "appr_1"},
            {"name": "To", "value": "evil@b.com"},
            {"name": "Subject", "value": "Subj"},
        ], "Body")):
            assert asyncio.run(reconcile_gmail_draft("u1", "appr_1", "a@b.com", "Subj", "Body")) is None

        # 4. No marker -> None
        with patch("httpx.AsyncClient", return_value=_mock_client([
            {"name": "To", "value": "a@b.com"},
            {"name": "Subject", "value": "Subj"},
        ], "Body")):
            assert asyncio.run(reconcile_gmail_draft("u1", "appr_1", "a@b.com", "Subj", "Body")) is None


def test_concurrent_email_draft_approve_only_creates_once():
    import asyncio
    import threading
    from concurrent.futures import ThreadPoolExecutor

    init_db()
    uid = "test_pr4_conc_user"
    _setup_user(uid, "pr4conc@example.com")
    conn = get_db()
    conn.execute(
        """
        INSERT INTO user_approvals (id, user_id, type, target, subject, reason, risk_level, draft_content, status, created_at)
        VALUES ('appr_conc_1', ?, 'Email Draft', 'a@b.com', 'Subj', 'Reason', 'Medium', 'Body', 'pending', datetime('now'))
        """,
        (uid,),
    )
    conn.commit()
    conn.close()

    async def _slow_create(*args, **kwargs):
        await asyncio.sleep(0.2)
        return "draft_concurrent_1"

    mock_create = AsyncMock(side_effect=_slow_create)
    barrier = threading.Barrier(2)

    def _call():
        c = _client_for(uid)
        barrier.wait(timeout=5)
        return c.post("/api/user/approvals/appr_conc_1/action", json={"action": "approve"})

    with patch("backend.google_service.create_gmail_draft", new=mock_create):
        with patch("backend.google_service.reconcile_gmail_draft", new=AsyncMock(return_value=None)):
            with ThreadPoolExecutor(max_workers=2) as pool:
                r1, r2 = list(pool.map(lambda _: _call(), range(2)))

    assert mock_create.call_count == 1
    assert 200 in (r1.status_code, r2.status_code)
    conn = get_db()
    row = conn.execute("SELECT status, gmail_draft_id FROM user_approvals WHERE id = 'appr_conc_1'").fetchone()
    conn.close()
    assert row["status"] == "approved"
    assert row["gmail_draft_id"] == "draft_concurrent_1"


def test_log_run_step_same_millisecond_no_collision(monkeypatch):
    import time as time_mod
    from backend.orchestrator import log_run_step

    init_db()
    uid = "test_orch_same_ms"
    _setup_user(uid, "orchms@example.com")
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO agent_runs (id, user_id, trigger_type, status, started_at) VALUES ('run_ms_1', ?, 'manual', 'running', datetime('now'))",
        (uid,),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(time_mod, "time", lambda: 1700000000.123)
    log_run_step(
        run_id="run_ms_1",
        user_id=uid,
        step_number=1,
        step_name="Step One",
        tool_name=None,
        policy_decision="Allowed",
        status="completed",
        result="ok1",
        tool_parameters=None,
        approval_required=False,
        latency_ms="1ms",
    )
    log_run_step(
        run_id="run_ms_1",
        user_id=uid,
        step_number=2,
        step_name="Step Two",
        tool_name=None,
        policy_decision="Allowed",
        status="completed",
        result="ok2",
        tool_parameters=None,
        approval_required=False,
        latency_ms="1ms",
    )

    conn = get_db()
    rows = conn.execute("SELECT * FROM user_activity WHERE user_id = ?", (uid,)).fetchall()
    conn.close()
    assert len(rows) == 2


def test_log_run_step_insert_failure_logs_warning_and_does_not_raise(caplog):
    import logging
    from backend.orchestrator import log_run_step

    bad_conn = MagicMock()
    bad_conn.execute.side_effect = RuntimeError("disk full")
    with caplog.at_level(logging.WARNING):
        with patch("backend.orchestrator.get_db", return_value=bad_conn):
            log_run_step("run_fail_1", "u_fail", 1, "Step Fail", None, None, "Allowed", False, "failed", "err", "0ms")
    assert any("log_run_step failed" in rec.message for rec in caplog.records)
    assert bad_conn.rollback.called
    assert bad_conn.close.called


def test_execute_daily_run_lock_held_bounded_time(caplog):
    import asyncio
    import logging
    import sqlite3
    import time as time_mod
    import backend.database as db_mod
    from backend.orchestrator import execute_daily_run

    init_db()
    uid = "test_orch_lock"
    _setup_user(uid, "orchlock@example.com")

    lock_conn = sqlite3.connect(str(db_mod.DB_PATH), timeout=1.0)
    lock_conn.execute("BEGIN IMMEDIATE")
    t0 = time_mod.monotonic()
    try:
        with caplog.at_level(logging.WARNING):
            res = asyncio.run(execute_daily_run(uid, trigger_type="manual"))
    finally:
        lock_conn.rollback()
        lock_conn.close()
    elapsed = time_mod.monotonic() - t0

    assert res["success"] is False
    assert elapsed < 8.0
    assert any("Failed to record run failure" in rec.message for rec in caplog.records)
