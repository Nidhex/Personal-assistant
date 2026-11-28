"""
Targeted regression tests for Stage 2: Workspace Data Isolation Security Fix.
Verifies strict isolation across workspaces with identical display names,
legacy task backward compatibility, public share safety, and cross-user isolation.
"""

import os
import json
import asyncio
import unittest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from backend.main import app, get_db
from backend.security import generate_session_id, get_session_expiry
from backend.agent import build_context, execute_policy_gate_and_tools


class TestWorkspaceDataIsolation(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.conn = get_db()
        self.cursor = self.conn.cursor()

        self.user_a = "usr_stage2_alice"
        self.user_b = "usr_stage2_bob"
        self.sess_a = self._create_user(self.user_a, "alice@stage2.test")
        self.sess_b = self._create_user(self.user_b, "bob@stage2.test")

    def tearDown(self):
        self.cursor.execute("DELETE FROM user_tasks WHERE user_id LIKE 'usr_stage2_%'")
        self.cursor.execute("DELETE FROM user_approvals WHERE user_id LIKE 'usr_stage2_%'")
        self.cursor.execute("DELETE FROM user_activity WHERE user_id LIKE 'usr_stage2_%'")
        self.cursor.execute("DELETE FROM user_revision_plans WHERE user_id LIKE 'usr_stage2_%'")
        self.cursor.execute("DELETE FROM user_study_materials WHERE user_id LIKE 'usr_stage2_%'")
        self.cursor.execute("DELETE FROM user_workspaces WHERE user_id LIKE 'usr_stage2_%'")
        self.cursor.execute("DELETE FROM user_workspace_notes WHERE user_id LIKE 'usr_stage2_%'")
        self.cursor.execute("DELETE FROM workspace_shares WHERE user_id LIKE 'usr_stage2_%'")
        self.cursor.execute("DELETE FROM sessions WHERE user_id LIKE 'usr_stage2_%'")
        self.cursor.execute("DELETE FROM users WHERE id LIKE 'usr_stage2_%'")
        self.conn.commit()
        self.conn.close()

    def _create_user(self, user_id: str, email: str) -> str:
        now_str = datetime.now(timezone.utc).isoformat()
        self.cursor.execute("""
            INSERT INTO users (id, email, name, picture, created_at)
            VALUES (?, ?, ?, 'https://example.com/avatar.png', ?)
            ON CONFLICT(id) DO UPDATE SET email = excluded.email, name = excluded.name
        """, (user_id, email, user_id, now_str))

        session_id = generate_session_id()
        expires_at = get_session_expiry(7)
        self.cursor.execute("""
            INSERT INTO sessions (session_id, user_id, expires_at, created_at)
            VALUES (?, ?, ?, ?)
        """, (session_id, user_id, expires_at, now_str))
        self.conn.commit()
        return session_id

    def _create_workspace(self, user_id: str, name: str, ws_id: str):
        now_str = datetime.now(timezone.utc).isoformat()
        self.cursor.execute("""
            INSERT INTO user_workspaces (id, user_id, name, type, description, created_at)
            VALUES (?, ?, ?, 'General', 'Test Workspace', ?)
        """, (ws_id, user_id, name, now_str))
        self.conn.commit()

    def _insert_task(self, user_id: str, task_id: str, title: str, workspace_ref: str):
        now_str = datetime.now(timezone.utc).isoformat()
        self.cursor.execute("""
            INSERT INTO user_tasks (id, user_id, title, source, due_date, priority, completed, workspace, created_at)
            VALUES (?, ?, ?, 'Manual', 'Tomorrow', 'normal', 0, ?, ?)
        """, (task_id, user_id, title, workspace_ref, now_str))
        self.conn.commit()

    # -------------------------------------------------------------
    # TEST A: Duplicate names, same user
    # -------------------------------------------------------------
    def test_A_duplicate_names_same_user_export_isolation(self):
        """Exporting Workspace A must never include Workspace B tasks when both share the same name."""
        ws1_id = "ws_alice_math_1"
        ws2_id = "ws_alice_math_2"
        self._create_workspace(self.user_a, "Mathematics", ws1_id)
        self._create_workspace(self.user_a, "Mathematics", ws2_id)

        self._insert_task(self.user_a, "tsk_m1", "Calculus Assignment", ws1_id)
        self._insert_task(self.user_a, "tsk_m2", "Linear Algebra Exam", ws2_id)

        res = self.client.get(f"/api/user/workspaces/{ws1_id}/export", cookies={"session_id": self.sess_a})
        self.assertEqual(res.status_code, 200)
        data = res.json()

        titles = [t["title"] for t in data["tasks"]]
        self.assertIn("Calculus Assignment", titles)
        self.assertNotIn("Linear Algebra Exam", titles)

    # -------------------------------------------------------------
    # TEST B: Public share isolation
    # -------------------------------------------------------------
    def test_B_public_share_isolation_with_duplicate_names(self):
        """Public share link for Workspace A must never expose Workspace B tasks with the same name."""
        ws_pub_id = "ws_alice_bio_public"
        ws_priv_id = "ws_alice_bio_private"
        self._create_workspace(self.user_a, "Biology", ws_pub_id)
        self._create_workspace(self.user_a, "Biology", ws_priv_id)

        self._insert_task(self.user_a, "tsk_pub", "Public Lab Report", ws_pub_id)
        self._insert_task(self.user_a, "tsk_priv", "Confidential Medical Notes", ws_priv_id)

        # Alice creates a share link for the public workspace
        res_share = self.client.post(f"/api/user/workspaces/{ws_pub_id}/share", cookies={"session_id": self.sess_a})
        self.assertEqual(res_share.status_code, 200)
        token = res_share.json()["token"]

        # An unauthenticated viewer accesses the shared workspace
        res_view = self.client.get(f"/api/shared/workspaces/{token}")
        self.assertEqual(res_view.status_code, 200)
        data = res_view.json()

        titles = [t["title"] for t in data["tasks"]]
        self.assertIn("Public Lab Report", titles)
        self.assertNotIn("Confidential Medical Notes", titles)

    # -------------------------------------------------------------
    # TEST C: Legacy task compatibility
    # -------------------------------------------------------------
    def test_C_legacy_task_compatibility_for_unique_workspace_name(self):
        """When a workspace name is unique for the user, legacy tasks storing ws_name are safely included."""
        ws_id = "ws_alice_astronomy"
        self._create_workspace(self.user_a, "Astronomy", ws_id)

        # Legacy task storing workspace name 'Astronomy' rather than 'ws_alice_astronomy'
        self._insert_task(self.user_a, "tsk_legacy", "Observe Lunar Eclipse", "Astronomy")

        # 1. Export includes the legacy task
        res_exp = self.client.get(f"/api/user/workspaces/{ws_id}/export", cookies={"session_id": self.sess_a})
        self.assertEqual(res_exp.status_code, 200)
        exp_titles = [t["title"] for t in res_exp.json()["tasks"]]
        self.assertIn("Observe Lunar Eclipse", exp_titles)

        # 2. Public share includes the legacy task
        res_share = self.client.post(f"/api/user/workspaces/{ws_id}/share", cookies={"session_id": self.sess_a})
        token = res_share.json()["token"]
        res_view = self.client.get(f"/api/shared/workspaces/{token}")
        self.assertEqual(res_view.status_code, 200)
        view_titles = [t["title"] for t in res_view.json()["tasks"]]
        self.assertIn("Observe Lunar Eclipse", view_titles)

    # -------------------------------------------------------------
    # TEST D: Ambiguous legacy tasks
    # -------------------------------------------------------------
    def test_D_ambiguous_legacy_tasks_are_never_exposed(self):
        """When two workspaces share a name, ambiguous legacy tasks associated with that name are excluded from both."""
        ws1_id = "ws_alice_chem_1"
        ws2_id = "ws_alice_chem_2"
        self._create_workspace(self.user_a, "Chemistry", ws1_id)
        self._create_workspace(self.user_a, "Chemistry", ws2_id)

        # Legacy task ambiguous between the two Chemistry workspaces
        self._insert_task(self.user_a, "tsk_ambiguous", "Ambiguous Chemistry Task", "Chemistry")

        # Check export of Workspace 1
        res1 = self.client.get(f"/api/user/workspaces/{ws1_id}/export", cookies={"session_id": self.sess_a})
        self.assertEqual(res1.status_code, 200)
        self.assertNotIn("Ambiguous Chemistry Task", [t["title"] for t in res1.json()["tasks"]])

        # Check export of Workspace 2
        res2 = self.client.get(f"/api/user/workspaces/{ws2_id}/export", cookies={"session_id": self.sess_a})
        self.assertEqual(res2.status_code, 200)
        self.assertNotIn("Ambiguous Chemistry Task", [t["title"] for t in res2.json()["tasks"]])

        # Check public share of Workspace 1
        res_share = self.client.post(f"/api/user/workspaces/{ws1_id}/share", cookies={"session_id": self.sess_a})
        token = res_share.json()["token"]
        res_view = self.client.get(f"/api/shared/workspaces/{token}")
        self.assertEqual(res_view.status_code, 200)
        self.assertNotIn("Ambiguous Chemistry Task", [t["title"] for t in res_view.json()["tasks"]])

    # -------------------------------------------------------------
    # TEST E: Different users
    # -------------------------------------------------------------
    def test_E_different_users_with_identical_workspace_names(self):
        """Different users having workspaces with identical names never leak tasks to each other."""
        ws_a = "ws_alice_history"
        ws_b = "ws_bob_history"
        self._create_workspace(self.user_a, "History", ws_a)
        self._create_workspace(self.user_b, "History", ws_b)

        self._insert_task(self.user_a, "tsk_a", "Alice History Essay", ws_a)
        self._insert_task(self.user_b, "tsk_b", "Bob History Quiz", ws_b)

        # Alice exports her History workspace
        res_a = self.client.get(f"/api/user/workspaces/{ws_a}/export", cookies={"session_id": self.sess_a})
        self.assertEqual(res_a.status_code, 200)
        titles_a = [t["title"] for t in res_a.json()["tasks"]]
        self.assertIn("Alice History Essay", titles_a)
        self.assertNotIn("Bob History Quiz", titles_a)

        # Bob exports his History workspace
        res_b = self.client.get(f"/api/user/workspaces/{ws_b}/export", cookies={"session_id": self.sess_b})
        self.assertEqual(res_b.status_code, 200)
        titles_b = [t["title"] for t in res_b.json()["tasks"]]
        self.assertIn("Bob History Quiz", titles_b)
        self.assertNotIn("Alice History Essay", titles_b)

    # -------------------------------------------------------------
    # TEST F: Unauthorized workspace access
    # -------------------------------------------------------------
    def test_F_unauthorized_workspace_access_rejected(self):
        """User B cannot export or share User A's workspace."""
        ws_a = "ws_alice_private_vault"
        self._create_workspace(self.user_a, "Vault", ws_a)

        # User B attempts to export Alice's workspace
        res_exp = self.client.get(f"/api/user/workspaces/{ws_a}/export", cookies={"session_id": self.sess_b})
        self.assertEqual(res_exp.status_code, 404)

        # User B attempts to share Alice's workspace
        res_share = self.client.post(f"/api/user/workspaces/{ws_a}/share", cookies={"session_id": self.sess_b})
        self.assertEqual(res_share.status_code, 404)

        # Invalid share token
        res_bad_tok = self.client.get("/api/shared/workspaces/invalid_nonexistent_token_12345")
        self.assertEqual(res_bad_tok.status_code, 404)

    # -------------------------------------------------------------
    # TEST G: Agent context isolation
    # -------------------------------------------------------------
    def test_G_agent_context_isolation_with_duplicate_workspace_names(self):
        """Agent context retrieval for duplicate-name workspaces does not bleed tasks across workspaces."""
        ws1_id = "ws_alice_agent_ws1"
        ws2_id = "ws_alice_agent_ws2"
        self._create_workspace(self.user_a, "Research", ws1_id)
        self._create_workspace(self.user_a, "Research", ws2_id)

        self._insert_task(self.user_a, "tsk_r1", "Research Task One", ws1_id)
        self._insert_task(self.user_a, "tsk_r2", "Research Task Two", ws2_id)

        # Retrieve agent context for workspace 1
        ctx1 = build_context(user_id=self.user_a, query="What tasks do I have?", workspace_id=ws1_id)
        tasks1 = [t["title"] for t in ctx1.get("tasks", [])]
        self.assertIn("Research Task One", tasks1)
        self.assertNotIn("Research Task Two", tasks1)

        # Retrieve agent context for workspace 2
        ctx2 = build_context(user_id=self.user_a, query="What tasks do I have?", workspace_id=ws2_id)
        tasks2 = [t["title"] for t in ctx2.get("tasks", [])]
        self.assertIn("Research Task Two", tasks2)
        self.assertNotIn("Research Task One", tasks2)

    # -------------------------------------------------------------
    # TEST H: Normal functionality
    # -------------------------------------------------------------
    def test_H_normal_workspace_import_export_sharing_lifecycle(self):
        """Normal workspace creation, task assignment, import, export, and sharing lifecycle work seamlessly."""
        # 1. Create task with workspace reference to an existing workspace
        ws_id = "ws_alice_lifecycle"
        self._create_workspace(self.user_a, "Lifecycle Project", ws_id)

        res_task = self.client.post("/api/user/tasks", json={
            "title": "Build Architecture Diagram",
            "due_date": "Next Friday",
            "priority": "high",
            "workspace": ws_id
        }, cookies={"session_id": self.sess_a})
        self.assertEqual(res_task.status_code, 200)

        # 2. Export workspace
        res_exp = self.client.get(f"/api/user/workspaces/{ws_id}/export", cookies={"session_id": self.sess_a})
        self.assertEqual(res_exp.status_code, 200)
        exp_data = res_exp.json()
        self.assertEqual(exp_data["workspace"]["name"], "Lifecycle Project")
        self.assertEqual(len(exp_data["tasks"]), 1)
        self.assertEqual(exp_data["tasks"][0]["title"], "Build Architecture Diagram")

        # 3. Import into new workspace
        res_imp = self.client.post("/api/user/workspaces/import", json={
            "workspace": {"name": "Imported Lifecycle", "type": "General", "description": "Imported"},
            "notes": [{"title": "Note 1", "content": "Hello World"}],
            "tasks": [{"title": "Imported Subtask", "due_date": "Today", "priority": "normal", "completed": False}]
        }, cookies={"session_id": self.sess_a})
        self.assertEqual(res_imp.status_code, 200)
        new_ws_id = res_imp.json()["workspace_id"]

        # Export imported workspace - assert task is canonically tied to new_ws_id
        res_exp_new = self.client.get(f"/api/user/workspaces/{new_ws_id}/export", cookies={"session_id": self.sess_a})
        self.assertEqual(res_exp_new.status_code, 200)
        self.assertEqual(len(res_exp_new.json()["tasks"]), 1)
        self.assertEqual(res_exp_new.json()["tasks"][0]["title"], "Imported Subtask")

        # 4. Revoke share link
        res_share = self.client.post(f"/api/user/workspaces/{new_ws_id}/share", cookies={"session_id": self.sess_a})
        token = res_share.json()["token"]

        res_revoke = self.client.delete(f"/api/user/workspaces/{new_ws_id}/share", cookies={"session_id": self.sess_a})
        self.assertEqual(res_revoke.status_code, 200)

        # After revoke, token access returns 404
        res_view_revoked = self.client.get(f"/api/shared/workspaces/{token}")
        self.assertEqual(res_view_revoked.status_code, 404)

    # -------------------------------------------------------------
    # STAGE 2 CORRECTION REGRESSION TESTS
    # -------------------------------------------------------------
    def test_I_agent_task_creation_with_valid_workspace_id_stores_id(self):
        """Agent task creation using a valid workspace ID stores that canonical ID."""
        ws_id = "ws_alice_valid_id"
        self._create_workspace(self.user_a, "Biology", ws_id)

        model_output = json.dumps({
            "action": {
                "tool": "create_task",
                "parameters": {
                    "title": "Study Cell Mitosis",
                    "due_date": "Tomorrow",
                    "priority": "normal",
                    "workspace": ws_id
                }
            }
        })
        res = asyncio.run(execute_policy_gate_and_tools(model_output, user_id=self.user_a))
        self.assertEqual(res["policy_decision"], "Allowed & Executed")

        row = self.cursor.execute(
            "SELECT workspace, title FROM user_tasks WHERE user_id = ? AND title = 'Study Cell Mitosis'",
            (self.user_a,)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["workspace"], ws_id)

    def test_J_agent_task_creation_with_unique_workspace_name_resolves_correctly(self):
        """Agent task creation using a unique workspace name resolves to the canonical workspace ID."""
        ws_id = "ws_alice_chemistry"
        self._create_workspace(self.user_a, "Chemistry", ws_id)

        model_output = json.dumps({
            "action": {
                "tool": "create_task",
                "parameters": {
                    "title": "Memorize Periodic Table",
                    "due_date": "Next Monday",
                    "priority": "high",
                    "workspace": "Chemistry"
                }
            }
        })
        res = asyncio.run(execute_policy_gate_and_tools(model_output, user_id=self.user_a))
        self.assertEqual(res["policy_decision"], "Allowed & Executed")

        row = self.cursor.execute(
            "SELECT workspace, title FROM user_tasks WHERE user_id = ? AND title = 'Memorize Periodic Table'",
            (self.user_a,)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["workspace"], ws_id)

    def test_K_agent_task_creation_with_duplicate_workspace_name_rejects_safely(self):
        """Agent task creation using a duplicate workspace name does not arbitrarily choose either workspace."""
        ws1_id = "ws_alice_dup_study_1"
        ws2_id = "ws_alice_dup_study_2"
        self._create_workspace(self.user_a, "Study", ws1_id)
        self._create_workspace(self.user_a, "Study", ws2_id)

        model_output = json.dumps({
            "action": {
                "tool": "create_task",
                "parameters": {
                    "title": "Ambiguous Study Session",
                    "due_date": "Today",
                    "workspace": "Study"
                }
            }
        })
        res = asyncio.run(execute_policy_gate_and_tools(model_output, user_id=self.user_a))
        self.assertEqual(res["policy_decision"], "Refused: Ambiguous workspace name")
        self.assertIn("Ambiguity Refusal", res["text"])

        # Neither workspace arbitrarily received the task
        row = self.cursor.execute(
            "SELECT id FROM user_tasks WHERE user_id = ? AND title = 'Ambiguous Study Session'",
            (self.user_a,)
        ).fetchone()
        self.assertIsNone(row)

    def test_L_cross_user_workspace_ids_are_rejected(self):
        """Cross-user workspace IDs are rejected and do not silently fall back to General."""
        ws_bob_id = "ws_bob_secret_project"
        self._create_workspace(self.user_b, "Bob Private", ws_bob_id)

        # 1. Parameter workspace target
        model_output = json.dumps({
            "action": {
                "tool": "create_task",
                "parameters": {
                    "title": "Cross User Task Attempt",
                    "workspace": ws_bob_id
                }
            }
        })
        res = asyncio.run(execute_policy_gate_and_tools(model_output, user_id=self.user_a))
        self.assertEqual(res["policy_decision"], "Refused: Access denied to workspace")

        # Verify no task was created under User A or User B
        row = self.cursor.execute(
            "SELECT id FROM user_tasks WHERE title = 'Cross User Task Attempt'"
        ).fetchone()
        self.assertIsNone(row)

        # 2. Context workspace_id
        res_ctx = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "create_task", "parameters": {"title": "Context Bypass Task"}}}),
            user_id=self.user_a,
            workspace_id=ws_bob_id
        ))
        self.assertEqual(res_ctx["policy_decision"], "Refused: Access denied to workspace")
        row_ctx = self.cursor.execute(
            "SELECT id FROM user_tasks WHERE title = 'Context Bypass Task'"
        ).fetchone()
        self.assertIsNone(row_ctx)

    def test_M_existing_task_creation_in_general_still_works(self):
        """Existing task creation in General (omitted workspace or explicit 'General') still works."""
        # 1. Omitted workspace
        model_output1 = json.dumps({
            "action": {
                "tool": "create_task",
                "parameters": {
                    "title": "Default General Task",
                    "due_date": "Today"
                }
            }
        })
        res1 = asyncio.run(execute_policy_gate_and_tools(model_output1, user_id=self.user_a))
        self.assertEqual(res1["policy_decision"], "Allowed & Executed")

        row1 = self.cursor.execute(
            "SELECT workspace FROM user_tasks WHERE user_id = ? AND title = 'Default General Task'",
            (self.user_a,)
        ).fetchone()
        self.assertIsNotNone(row1)
        self.assertEqual(row1["workspace"], "General")

        # 2. Explicit 'General'
        model_output2 = json.dumps({
            "action": {
                "tool": "create_task",
                "parameters": {
                    "title": "Explicit General Task",
                    "workspace": "General"
                }
            }
        })
        res2 = asyncio.run(execute_policy_gate_and_tools(model_output2, user_id=self.user_a))
        self.assertEqual(res2["policy_decision"], "Allowed & Executed")

        row2 = self.cursor.execute(
            "SELECT workspace FROM user_tasks WHERE user_id = ? AND title = 'Explicit General Task'",
            (self.user_a,)
        ).fetchone()
        self.assertIsNotNone(row2)
        self.assertEqual(row2["workspace"], "General")

    def test_N_proposed_tasks_cannot_bypass_workspace_validation_when_approved(self):
        """Proposed tasks cannot bypass workspace validation when approved."""
        ws_bob_id = "ws_bob_confidential"
        self._create_workspace(self.user_b, "Bob Confidential", ws_bob_id)

        # 1. An approval record attempting to assign a task to Bob's workspace fails upon approval
        appr_id = "appr_test_cross_user_1"
        payload_illegal = {
            "title": "Trojan Task in Bob WS",
            "due_date": "Today",
            "priority": "normal",
            "workspace": ws_bob_id
        }
        self.cursor.execute("""
            INSERT INTO user_approvals (id, user_id, type, target, subject, reason, risk_level, draft_content, status, created_at)
            VALUES (?, ?, 'Task Proposal', 'Trojan Task in Bob WS', 'Test Subject', 'Reason', 'Low', ?, 'pending', datetime('now'))
        """, (appr_id, self.user_a, json.dumps(payload_illegal)))
        self.conn.commit()

        res_approve = self.client.post(f"/api/user/approvals/{appr_id}/action", json={"action": "approve"}, cookies={"session_id": self.sess_a})
        self.assertEqual(res_approve.status_code, 403)

        # Task was NOT created
        row = self.cursor.execute("SELECT id FROM user_tasks WHERE title = 'Trojan Task in Bob WS'").fetchone()
        self.assertIsNone(row)

        # 2. An approval record with duplicate ambiguous workspace name fails upon approval
        ws_dup1 = "ws_alice_plan_1"
        ws_dup2 = "ws_alice_plan_2"
        self._create_workspace(self.user_a, "Ambiguous Workspace", ws_dup1)
        self._create_workspace(self.user_a, "Ambiguous Workspace", ws_dup2)

        appr_id2 = "appr_test_ambig_2"
        payload_ambig = {
            "title": "Ambiguous Proposed Task",
            "due_date": "Today",
            "priority": "normal",
            "workspace": "Ambiguous Workspace"
        }
        self.cursor.execute("""
            INSERT INTO user_approvals (id, user_id, type, target, subject, reason, risk_level, draft_content, status, created_at)
            VALUES (?, ?, 'Task Proposal', 'Ambiguous Proposed Task', 'Test Subject', 'Reason', 'Low', ?, 'pending', datetime('now'))
        """, (appr_id2, self.user_a, json.dumps(payload_ambig)))
        self.conn.commit()

        res_approve2 = self.client.post(f"/api/user/approvals/{appr_id2}/action", json={"action": "approve"}, cookies={"session_id": self.sess_a})
        self.assertEqual(res_approve2.status_code, 400)

        # Task was NOT created
        row2 = self.cursor.execute("SELECT id FROM user_tasks WHERE title = 'Ambiguous Proposed Task'").fetchone()
        self.assertIsNone(row2)

        # 3. propose_task agent tool rejects ambiguous duplicate workspace name at creation time
        model_output_prop = json.dumps({
            "action": {
                "tool": "propose_task",
                "parameters": {
                    "title": "Direct Proposed Ambiguous",
                    "workspace": "Ambiguous Workspace"
                }
            }
        })
        res_prop = asyncio.run(execute_policy_gate_and_tools(model_output_prop, user_id=self.user_a))
        self.assertEqual(res_prop["policy_decision"], "Refused: Ambiguous workspace name")
        self.assertFalse(res_prop["approval_required"])

        # No approval row was inserted
        row_appr = self.cursor.execute("SELECT id FROM user_approvals WHERE target = 'Direct Proposed Ambiguous'").fetchone()
        self.assertIsNone(row_appr)

    # -------------------------------------------------------------
    # REVISION PLAN WORKSPACE ISOLATION TESTS
    # -------------------------------------------------------------
    def test_O_duplicate_workspaces_never_retrieve_each_others_revision_plans(self):
        """Two workspaces with the same name must never retrieve each other's revision plans."""
        ws_bio_1 = "ws_alice_bio_1"
        ws_bio_2 = "ws_alice_bio_2"
        self._create_workspace(self.user_a, "Biology", ws_bio_1)
        self._create_workspace(self.user_a, "Biology", ws_bio_2)

        # Plan belongs strictly to ws_bio_1
        plan_sessions = [{"session_number": 1, "topic": "Cell Structure", "date": "2026-12-01"}]
        self.cursor.execute("""
            INSERT INTO user_revision_plans (id, user_id, workspace_id, exam_date, plan_json, created_at, updated_at)
            VALUES ('plan_bio_1', ?, ?, '2026-12-15', ?, datetime('now'), datetime('now'))
        """, (self.user_a, ws_bio_1, json.dumps(plan_sessions)))
        self.conn.commit()

        # Querying ws_bio_2 via API endpoint must return None
        res2 = self.client.get(f"/api/user/workspaces/{ws_bio_2}/revision-plan", cookies={"session_id": self.sess_a})
        self.assertEqual(res2.status_code, 200)
        self.assertIsNone(res2.json()["plan"])

        # Agent context for ws_bio_2 must NOT include ws_bio_1's plan
        ctx2 = build_context(user_id=self.user_a, workspace_id=ws_bio_2)
        self.assertEqual(len(ctx2.get("revision_plans", [])), 0)

        # Querying ws_bio_1 must return the plan
        res1 = self.client.get(f"/api/user/workspaces/{ws_bio_1}/revision-plan", cookies={"session_id": self.sess_a})
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json()["plan"]["id"], "plan_bio_1")

        ctx1 = build_context(user_id=self.user_a, workspace_id=ws_bio_1)
        self.assertEqual(len(ctx1.get("revision_plans", [])), 1)
        self.assertEqual(ctx1["revision_plans"][0]["id"], "plan_bio_1")

    def test_P_revision_plan_belonging_to_workspace_a_not_converted_in_workspace_b(self):
        """A revision plan belonging to workspace A must not be converted in workspace B."""
        ws_bio_1 = "ws_alice_bio_a"
        ws_bio_2 = "ws_alice_bio_b"
        self._create_workspace(self.user_a, "Biology", ws_bio_1)
        self._create_workspace(self.user_a, "Biology", ws_bio_2)

        # Plan created in ws_bio_1
        plan_sessions = [{"session_number": 1, "topic": "Genetics & DNA", "date": "2026-12-03"}]
        self.cursor.execute("""
            INSERT INTO user_revision_plans (id, user_id, workspace_id, exam_date, plan_json, created_at, updated_at)
            VALUES ('plan_bio_a', ?, ?, '2026-12-15', ?, datetime('now'), datetime('now'))
        """, (self.user_a, ws_bio_1, json.dumps(plan_sessions)))
        self.conn.commit()

        # Try to convert plan in ws_bio_2
        res = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "convert_plan_to_tasks"}}),
            user_id=self.user_a,
            workspace_id=ws_bio_2
        ))
        self.assertEqual(res["policy_decision"], "No Revision Plan Found")

        # No tasks should be created in ws_bio_2
        tasks_ws2 = self.cursor.execute("SELECT id FROM user_tasks WHERE user_id = ? AND workspace = ?", (self.user_a, ws_bio_2)).fetchall()
        self.assertEqual(len(tasks_ws2), 0)

    def test_Q_unique_name_legacy_revision_plans_still_work(self):
        """Unique-name legacy revision plans (where workspace_id stored display name) must still work."""
        ws_hist_id = "ws_alice_history_unique"
        self._create_workspace(self.user_a, "History", ws_hist_id)

        # Legacy plan stored with workspace_id = 'History'
        plan_sessions = [{"session_number": 1, "topic": "French Revolution", "date": "2026-12-02"}]
        self.cursor.execute("""
            INSERT INTO user_revision_plans (id, user_id, workspace_id, exam_date, plan_json, created_at, updated_at)
            VALUES ('plan_hist_legacy', ?, 'History', '2026-12-20', ?, datetime('now'), datetime('now'))
        """, (self.user_a, json.dumps(plan_sessions)))
        self.conn.commit()

        # Endpoint resolves legacy plan when name is unique
        res = self.client.get(f"/api/user/workspaces/{ws_hist_id}/revision-plan", cookies={"session_id": self.sess_a})
        self.assertEqual(res.status_code, 200)
        self.assertIsNotNone(res.json()["plan"])
        self.assertEqual(res.json()["plan"]["id"], "plan_hist_legacy")

        # convert_plan_to_tasks resolves legacy plan and creates task with canonical ws ID
        res_conv = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "convert_plan_to_tasks"}}),
            user_id=self.user_a,
            workspace_id=ws_hist_id
        ))
        self.assertEqual(res_conv["policy_decision"], "Allowed & Executed")

        task = self.cursor.execute(
            "SELECT workspace, title FROM user_tasks WHERE user_id = ? AND title = 'Revision Session: French Revolution'",
            (self.user_a,)
        ).fetchone()
        self.assertIsNotNone(task)
        self.assertEqual(task["workspace"], ws_hist_id)

    def test_R_task_in_duplicate_name_workspace_does_not_block_task_in_other(self):
        """A task in one duplicate-name workspace must not block task creation in another workspace with the same display name."""
        ws_phys_1 = "ws_alice_phys_1"
        ws_phys_2 = "ws_alice_phys_2"
        self._create_workspace(self.user_a, "Physics", ws_phys_1)
        self._create_workspace(self.user_a, "Physics", ws_phys_2)

        # Both workspaces have a revision plan covering 'Quantum Mechanics'
        plan_q = [{"session_number": 1, "topic": "Quantum Mechanics", "date": "2026-12-05"}]
        self.cursor.execute("""
            INSERT INTO user_revision_plans (id, user_id, workspace_id, exam_date, plan_json, created_at, updated_at)
            VALUES ('plan_phys_1', ?, ?, '2026-12-18', ?, datetime('now'), datetime('now')),
                   ('plan_phys_2', ?, ?, '2026-12-18', ?, datetime('now'), datetime('now'))
        """, (self.user_a, ws_phys_1, json.dumps(plan_q), self.user_a, ws_phys_2, json.dumps(plan_q)))
        self.conn.commit()

        # Convert in workspace 1 -> creates task in ws_phys_1
        res1 = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "convert_plan_to_tasks"}}),
            user_id=self.user_a,
            workspace_id=ws_phys_1
        ))
        self.assertEqual(res1["policy_decision"], "Allowed & Executed")
        t1 = self.cursor.execute("SELECT id FROM user_tasks WHERE user_id = ? AND workspace = ?", (self.user_a, ws_phys_1)).fetchall()
        self.assertEqual(len(t1), 1)

        # Convert in workspace 2 -> task in ws_phys_1 must NOT suppress creation in ws_phys_2
        res2 = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "convert_plan_to_tasks"}}),
            user_id=self.user_a,
            workspace_id=ws_phys_2
        ))
        self.assertEqual(res2["policy_decision"], "Allowed & Executed")
        t2 = self.cursor.execute("SELECT id FROM user_tasks WHERE user_id = ? AND workspace = ?", (self.user_a, ws_phys_2)).fetchall()
        self.assertEqual(len(t2), 1)

    def test_S_general_workspace_revision_plan_behavior_intact(self):
        """Existing General workspace revision plan behavior remains fully intact."""
        plan_gen = [{"session_number": 1, "topic": "General Review", "date": "2026-12-10"}]
        self.cursor.execute("""
            INSERT INTO user_revision_plans (id, user_id, workspace_id, exam_date, plan_json, created_at, updated_at)
            VALUES ('plan_gen_test', ?, 'General', '2026-12-25', ?, datetime('now'), datetime('now'))
        """, (self.user_a, json.dumps(plan_gen)))
        self.conn.commit()

        # Query endpoint for General
        res = self.client.get("/api/user/workspaces/General/revision-plan", cookies={"session_id": self.sess_a})
        self.assertEqual(res.status_code, 200)
        self.assertIsNotNone(res.json()["plan"])
        self.assertEqual(res.json()["plan"]["id"], "plan_gen_test")

        # Convert in General workspace
        res_conv = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "convert_plan_to_tasks"}}),
            user_id=self.user_a,
            workspace_id="General"
        ))
        self.assertEqual(res_conv["policy_decision"], "Allowed & Executed")

        task = self.cursor.execute(
            "SELECT workspace, title FROM user_tasks WHERE user_id = ? AND title = 'Revision Session: General Review'",
            (self.user_a,)
        ).fetchone()
        self.assertIsNotNone(task)
        self.assertEqual(task["workspace"], "General")

    def test_T_create_task_duplicate_check_independent_across_duplicate_name_workspaces(self):
        """A task in workspace A cannot block task creation in workspace B even with identical display names."""
        ws_work_1 = "ws_alice_work_dup_1"
        ws_work_2 = "ws_alice_work_dup_2"
        self._create_workspace(self.user_a, "Work", ws_work_1)
        self._create_workspace(self.user_a, "Work", ws_work_2)

        # 1. Create task in workspace 1
        model_output1 = json.dumps({
            "action": {
                "tool": "create_task",
                "parameters": {
                    "title": "Quarterly Financial Review",
                    "due_date": "Tomorrow",
                    "workspace": ws_work_1
                }
            }
        })
        res1 = asyncio.run(execute_policy_gate_and_tools(model_output1, user_id=self.user_a))
        self.assertEqual(res1["policy_decision"], "Allowed & Executed")

        # 2. Create identical task title in workspace 2 -> MUST SUCCEED (not blocked by ws_work_1)
        model_output2 = json.dumps({
            "action": {
                "tool": "create_task",
                "parameters": {
                    "title": "Quarterly Financial Review",
                    "due_date": "Next Week",
                    "workspace": ws_work_2
                }
            }
        })
        res2 = asyncio.run(execute_policy_gate_and_tools(model_output2, user_id=self.user_a))
        self.assertEqual(res2["policy_decision"], "Allowed & Executed")

        # Verify both tasks exist with their respective canonical IDs
        t1 = self.cursor.execute("SELECT workspace FROM user_tasks WHERE user_id = ? AND workspace = ?", (self.user_a, ws_work_1)).fetchall()
        t2 = self.cursor.execute("SELECT workspace FROM user_tasks WHERE user_id = ? AND workspace = ?", (self.user_a, ws_work_2)).fetchall()
        self.assertEqual(len(t1), 1)
        self.assertEqual(len(t2), 1)

        # 3. Repeat creation in workspace 1 -> MUST BE BLOCKED by duplicate check within ws_work_1
        res3 = asyncio.run(execute_policy_gate_and_tools(model_output1, user_id=self.user_a))
        self.assertEqual(res3["policy_decision"], "Duplicate Check: Prevented Duplicate")

    def test_U_list_tasks_workspace_isolation_and_no_fuzzy_leak(self):
        """list_tasks strictly refuses unknown/partial names without fuzzy leakage, while preserving valid IDs, unique names, and General."""
        # Setup workspaces
        ws_bio_id = "ws_alice_bio_101"
        self._create_workspace(self.user_a, "Biology 101", ws_bio_id)
        self.cursor.execute("""
            INSERT INTO user_tasks (id, user_id, title, source, due_date, priority, completed, workspace, created_at)
            VALUES ('tsk_bio_read', ?, 'Read Campbell Biology', 'Manual', 'Tomorrow', 'normal', 0, ?, datetime('now'))
        """, (self.user_a, ws_bio_id))

        ws_art_id = "ws_alice_art_hist"
        self._create_workspace(self.user_a, "ArtHistory", ws_art_id)
        # Legacy task carrying unique display name
        self.cursor.execute("""
            INSERT INTO user_tasks (id, user_id, title, source, due_date, priority, completed, workspace, created_at)
            VALUES ('tsk_art_essay', ?, 'Renaissance Essay', 'Manual', 'Friday', 'high', 0, 'ArtHistory', datetime('now'))
        """, (self.user_a,))

        # Duplicate-name workspaces
        ws_lab1 = "ws_alice_duplab_1"
        ws_lab2 = "ws_alice_duplab_2"
        self._create_workspace(self.user_a, "DuplicateLab", ws_lab1)
        self._create_workspace(self.user_a, "DuplicateLab", ws_lab2)

        # General task
        self.cursor.execute("""
            INSERT INTO user_tasks (id, user_id, title, source, due_date, priority, completed, workspace, created_at)
            VALUES ('tsk_gen_rev', ?, 'General Weekly Review', 'Manual', 'Today', 'normal', 0, 'General', datetime('now'))
        """, (self.user_a,))
        self.conn.commit()

        # 1. Unknown workspace name must return refusal, no tasks
        res_unknown = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "list_tasks", "parameters": {"workspace": "NonExistentWorkspace"}}}),
            user_id=self.user_a
        ))
        self.assertEqual(res_unknown["policy_decision"], "Refused: Workspace not found")
        self.assertIn("Workspace 'NonExistentWorkspace' not found", res_unknown["text"])

        # 2. Partial name must not retrieve tasks from similarly named workspaces (no fuzzy SQL leak)
        res_partial = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "list_tasks", "parameters": {"workspace": "Bio"}}}),
            user_id=self.user_a
        ))
        self.assertEqual(res_partial["policy_decision"], "Refused: Workspace not found")
        self.assertNotIn("Read Campbell Biology", res_partial["text"])

        # 3. Valid workspace ID returns its own tasks
        res_id = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "list_tasks", "parameters": {"workspace": ws_bio_id}}}),
            user_id=self.user_a
        ))
        self.assertEqual(res_id["policy_decision"], "Allowed & Executed")
        self.assertIn("Read Campbell Biology", res_id["text"])

        # 4. Unique legacy workspace name remains compatible
        res_legacy = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "list_tasks", "parameters": {"workspace": "ArtHistory"}}}),
            user_id=self.user_a
        ))
        self.assertEqual(res_legacy["policy_decision"], "Allowed & Executed")
        self.assertIn("Renaissance Essay", res_legacy["text"])

        # 5. Duplicate names remain safely rejected with ambiguity refusal
        res_dup = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "list_tasks", "parameters": {"workspace": "DuplicateLab"}}}),
            user_id=self.user_a
        ))
        self.assertEqual(res_dup["policy_decision"], "Refused: Ambiguous workspace name")

        # 6. General workspace behavior remains intact
        res_gen = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "list_tasks", "parameters": {"workspace": "General"}}}),
            user_id=self.user_a
        ))
        self.assertEqual(res_gen["policy_decision"], "Allowed & Executed")
        self.assertIn("General Weekly Review", res_gen["text"])

    def test_V_exact_legacy_task_label_supported_only_in_list_tasks(self):
        """Exact legacy task labels are resolved only for list_tasks and rejected in write/study tools."""
        # Setup legacy task with no matching user_workspaces entity
        self.cursor.execute("""
            INSERT INTO user_tasks (id, user_id, title, source, due_date, priority, completed, workspace, created_at)
            VALUES ('tsk_leg_physics_1', ?, 'Solve Quantum Mechanics Assignment', 'Manual', 'Tomorrow', 'high', 0, 'PhysicsLegacy', datetime('now'))
        """, (self.user_a,))
        self.conn.commit()

        # 1. list_tasks explicitly supports exact legacy task labels
        res_list = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "list_tasks", "parameters": {"workspace": "PhysicsLegacy"}}}),
            user_id=self.user_a
        ))
        self.assertEqual(res_list["policy_decision"], "Allowed & Executed")
        self.assertIn("Solve Quantum Mechanics Assignment", res_list["text"])

        # 2. create_task rejects unverified legacy label
        res_create = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "create_task", "parameters": {"title": "New Physics Task", "workspace": "PhysicsLegacy"}}}),
            user_id=self.user_a
        ))
        self.assertEqual(res_create["policy_decision"], "Refused: Workspace not found")

        # 3. create_revision_plan rejects unverified legacy label
        res_plan = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "create_revision_plan", "parameters": {"exam_date": "2026-12-20", "workspace": "PhysicsLegacy"}}}),
            user_id=self.user_a
        ))
        self.assertEqual(res_plan["policy_decision"], "Refused: Workspace not found")

        # 4. generate_quiz_questions rejects unverified legacy label
        res_quiz = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "generate_quiz_questions", "parameters": {"workspace": "PhysicsLegacy"}}}),
            user_id=self.user_a
        ))
        self.assertEqual(res_quiz["policy_decision"], "Refused: Workspace not found")

        # 5. convert_plan_to_tasks rejects unverified legacy label
        res_convert = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "convert_plan_to_tasks", "parameters": {"workspace": "PhysicsLegacy"}}}),
            user_id=self.user_a
        ))
        self.assertEqual(res_convert["policy_decision"], "Refused: Workspace not found")

    def test_W_legacy_label_conflicts_with_workspace_name_or_id_fail_safe(self):
        """When legacy labels conflict with workspace identities or cross-user IDs, security checks take precedence."""
        # 1. Legacy label matching real workspace name resolves to real workspace canonical ID
        ws_real_id = "ws_alice_astro_99"
        self._create_workspace(self.user_a, "Astrophysics", ws_real_id)
        self.cursor.execute("""
            INSERT INTO user_tasks (id, user_id, title, source, due_date, priority, completed, workspace, created_at)
            VALUES ('tsk_astro_leg', ?, 'Study Stellar Spectra', 'Manual', 'Tomorrow', 'normal', 0, 'Astrophysics', datetime('now'))
        """, (self.user_a,))
        self.cursor.execute("""
            INSERT INTO user_tasks (id, user_id, title, source, due_date, priority, completed, workspace, created_at)
            VALUES ('tsk_astro_can', ?, 'Analyze Light Curve', 'Manual', 'Tomorrow', 'normal', 0, ?, datetime('now'))
        """, (self.user_a, ws_real_id))
        self.conn.commit()

        # Both legacy-labeled and canonical-labeled tasks are retrieved safely under the verified workspace
        res_astro = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "list_tasks", "parameters": {"workspace": "Astrophysics"}}}),
            user_id=self.user_a
        ))
        self.assertEqual(res_astro["policy_decision"], "Allowed & Executed")
        self.assertIn("Study Stellar Spectra", res_astro["text"])
        self.assertIn("Analyze Light Curve", res_astro["text"])

        # 2. Legacy label matching another user's workspace ID fails with cross_user refusal
        ws_bob_id = "ws_bob_classified_secret"
        self._create_workspace(self.user_b, "Bob Classified", ws_bob_id)
        # Alice maliciously or mistakenly has a legacy task storing Bob's workspace ID
        self.cursor.execute("""
            INSERT INTO user_tasks (id, user_id, title, source, due_date, priority, completed, workspace, created_at)
            VALUES ('tsk_alice_rogue', ?, 'Probing Bob Task', 'Manual', 'Today', 'high', 0, ?, datetime('now'))
        """, (self.user_a, ws_bob_id))
        self.conn.commit()

        res_cross = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "list_tasks", "parameters": {"workspace": ws_bob_id}}}),
            user_id=self.user_a
        ))
        self.assertEqual(res_cross["policy_decision"], "Refused: Access denied to workspace")

        # 3. Non-existent ID format (ws_...) is rejected (case-insensitively) and never falls back to legacy matching
        res_nonexistent = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "list_tasks", "parameters": {"workspace": "ws_nonexistent_999"}}}),
            user_id=self.user_a
        ))
        self.assertEqual(res_nonexistent["policy_decision"], "Refused: Workspace not found")

        res_uppercase_ws = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "list_tasks", "parameters": {"workspace": "WS_NONEXISTENT_888"}}}),
            user_id=self.user_a
        ))
        self.assertEqual(res_uppercase_ws["policy_decision"], "Refused: Workspace not found")

    def test_X_duplicate_legacy_labels_treated_as_ambiguous(self):
        """Conflicting duplicate legacy representations in user_tasks are rejected with ambiguity refusal."""
        # User has two distinct case-representations of legacy tasks with no workspace row
        self.cursor.execute("""
            INSERT INTO user_tasks (id, user_id, title, source, due_date, priority, completed, workspace, created_at)
            VALUES ('tsk_dup_leg_1', ?, 'Biochem Task 1', 'Manual', 'Today', 'normal', 0, 'BioChemistry', datetime('now'))
        """, (self.user_a,))
        self.cursor.execute("""
            INSERT INTO user_tasks (id, user_id, title, source, due_date, priority, completed, workspace, created_at)
            VALUES ('tsk_dup_leg_2', ?, 'Biochem Task 2', 'Manual', 'Today', 'normal', 0, 'BIOCHEMISTRY', datetime('now'))
        """, (self.user_a,))
        self.conn.commit()

        # Querying the legacy label returns ambiguity refusal rather than picking an arbitrary variant
        res_dup_legacy = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "list_tasks", "parameters": {"workspace": "biochemistry"}}}),
            user_id=self.user_a
        ))
        self.assertEqual(res_dup_legacy["policy_decision"], "Refused: Ambiguous workspace name")

    def test_Y_no_cross_workspace_study_material_or_task_leakage_via_legacy_label(self):
        """A legacy label cannot access, link, or leak notes or study materials from verified workspaces."""
        ws_valid_id = "ws_alice_neuro_01"
        self._create_workspace(self.user_a, "Neuroscience", ws_valid_id)
        # Upload secret study material in the verified workspace
        self.cursor.execute("""
            INSERT INTO user_workspace_notes (id, user_id, workspace_id, title, content, created_at, updated_at)
            VALUES ('note_neuro_1', ?, ?, 'Confidential Synapse Research', 'Secret chemical transmitter discovery', datetime('now'), datetime('now'))
        """, (self.user_a, ws_valid_id))
        self.cursor.execute("""
            INSERT INTO user_study_materials (id, user_id, workspace_id, filename, content_text, created_at)
            VALUES ('mat_neuro_1', ?, ?, 'neuro_lab.txt', 'Confidential axon terminal voltages', datetime('now'))
        """, (self.user_a, ws_valid_id))

        # Separate legacy task label
        self.cursor.execute("""
            INSERT INTO user_tasks (id, user_id, title, source, due_date, priority, completed, workspace, created_at)
            VALUES ('tsk_neuro_leg', ?, 'Neuro Review', 'Manual', 'Tomorrow', 'normal', 0, 'NeuroLegacyText', datetime('now'))
        """, (self.user_a,))
        self.conn.commit()

        # Attempting to generate quiz questions or revision plan using the legacy label fails closed
        res_quiz = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "generate_quiz_questions", "parameters": {"workspace": "NeuroLegacyText"}}}),
            user_id=self.user_a
        ))
        self.assertEqual(res_quiz["policy_decision"], "Refused: Workspace not found")
        self.assertNotIn("Confidential Synapse Research", res_quiz["text"])
        self.assertNotIn("Confidential axon terminal voltages", res_quiz["text"])

        # Listing tasks under the legacy label returns ONLY the legacy task and never tasks from other workspaces
        res_list = asyncio.run(execute_policy_gate_and_tools(
            model_output=json.dumps({"action": {"tool": "list_tasks", "parameters": {"workspace": "NeuroLegacyText"}}}),
            user_id=self.user_a
        ))
        self.assertEqual(res_list["policy_decision"], "Allowed & Executed")
        self.assertIn("Neuro Review", res_list["text"])
        self.assertNotIn("Confidential", res_list["text"])

    def test_Z_rest_api_case_insensitive_workspace_id_validation(self):
        """POST /api/user/tasks and PUT /api/user/tasks/{id} strictly reject uppercase/mixed-case invalid WS_ IDs while preserving valid IDs, General, unique names, and ad-hoc labels."""
        ws_bob_id = "ws_bob_private_target"
        self._create_workspace(self.user_b, "Bob Target", ws_bob_id)

        ws_alice_valid = "ws_alice_target_real"
        self._create_workspace(self.user_a, "Alice Unique Lab", ws_alice_valid)

        # 1. POST /api/user/tasks rejects uppercase and lowercase nonexistent IDs -> 404
        res_post_nonexistent = self.client.post("/api/user/tasks", json={
            "title": "Invalid Uppercase WS ID Task",
            "workspace": "WS_NONEXISTENT_999"
        }, cookies={"session_id": self.sess_a})
        self.assertEqual(res_post_nonexistent.status_code, 404)
        self.assertIn("Workspace not found", res_post_nonexistent.json()["detail"])

        res_post_nonexistent_lower = self.client.post("/api/user/tasks", json={
            "title": "Invalid Lowercase WS ID Task",
            "workspace": "ws_nonexistent_001"
        }, cookies={"session_id": self.sess_a})
        self.assertEqual(res_post_nonexistent_lower.status_code, 404)
        self.assertIn("Workspace not found", res_post_nonexistent_lower.json()["detail"])

        # 2. POST /api/user/tasks rejects mixed-case and lowercase another user's ID -> 403
        res_post_cross = self.client.post("/api/user/tasks", json={
            "title": "Cross User WS ID Task",
            "workspace": ws_bob_id.upper()
        }, cookies={"session_id": self.sess_a})
        self.assertEqual(res_post_cross.status_code, 403)
        self.assertIn("Access denied to workspace", res_post_cross.json()["detail"])

        res_post_cross_lower = self.client.post("/api/user/tasks", json={
            "title": "Cross User Lowercase WS ID Task",
            "workspace": ws_bob_id
        }, cookies={"session_id": self.sess_a})
        self.assertEqual(res_post_cross_lower.status_code, 403)
        self.assertIn("Access denied to workspace", res_post_cross_lower.json()["detail"])

        # 3. Create an initial task for Alice to test PUT
        res_init = self.client.post("/api/user/tasks", json={
            "title": "Alice Initial Task",
            "workspace": ws_alice_valid
        }, cookies={"session_id": self.sess_a})
        self.assertEqual(res_init.status_code, 200)
        task_id = res_init.json()["id"]

        # 4. PUT /api/user/tasks/{id} rejects uppercase and lowercase nonexistent IDs -> 404
        res_put_nonexistent = self.client.put(f"/api/user/tasks/{task_id}", json={
            "workspace": "Ws_nonexistent_888"
        }, cookies={"session_id": self.sess_a})
        self.assertEqual(res_put_nonexistent.status_code, 404)
        self.assertIn("Workspace not found", res_put_nonexistent.json()["detail"])

        res_put_nonexistent_lower = self.client.put(f"/api/user/tasks/{task_id}", json={
            "workspace": "ws_nonexistent_002"
        }, cookies={"session_id": self.sess_a})
        self.assertEqual(res_put_nonexistent_lower.status_code, 404)
        self.assertIn("Workspace not found", res_put_nonexistent_lower.json()["detail"])

        # 5. PUT /api/user/tasks/{id} rejects mixed-case and lowercase cross-user IDs -> 403
        res_put_cross = self.client.put(f"/api/user/tasks/{task_id}", json={
            "workspace": "Ws_" + ws_bob_id[3:]
        }, cookies={"session_id": self.sess_a})
        self.assertEqual(res_put_cross.status_code, 403)
        self.assertIn("Access denied to workspace", res_put_cross.json()["detail"])

        res_put_cross_lower = self.client.put(f"/api/user/tasks/{task_id}", json={
            "workspace": ws_bob_id
        }, cookies={"session_id": self.sess_a})
        self.assertEqual(res_put_cross_lower.status_code, 403)
        self.assertIn("Access denied to workspace", res_put_cross_lower.json()["detail"])

        # 6. Normal ad-hoc labels (e.g. Workspace_Alice) still work
        res_adhoc = self.client.post("/api/user/tasks", json={
            "title": "Alice Ad-Hoc Task",
            "workspace": "Workspace_Alice"
        }, cookies={"session_id": self.sess_a})
        self.assertEqual(res_adhoc.status_code, 200)
        adhoc_id = res_adhoc.json()["id"]
        adhoc_row = self.cursor.execute("SELECT workspace FROM user_tasks WHERE id = ?", (adhoc_id,)).fetchone()
        self.assertEqual(adhoc_row["workspace"], "Workspace_Alice")

        # 7. Valid workspace IDs work
        res_valid_id = self.client.post("/api/user/tasks", json={
            "title": "Alice Valid ID Task",
            "workspace": ws_alice_valid
        }, cookies={"session_id": self.sess_a})
        self.assertEqual(res_valid_id.status_code, 200)
        valid_id = res_valid_id.json()["id"]
        valid_row = self.cursor.execute("SELECT workspace FROM user_tasks WHERE id = ?", (valid_id,)).fetchone()
        self.assertEqual(valid_row["workspace"], ws_alice_valid)

        # 8. General workspace works
        res_gen = self.client.post("/api/user/tasks", json={
            "title": "Alice General Task",
            "workspace": "General"
        }, cookies={"session_id": self.sess_a})
        self.assertEqual(res_gen.status_code, 200)
        gen_id = res_gen.json()["id"]
        gen_row = self.cursor.execute("SELECT workspace FROM user_tasks WHERE id = ?", (gen_id,)).fetchone()
        self.assertEqual(gen_row["workspace"], "General")

        # 9. Unique workspace names resolve to canonical ID
        res_name = self.client.post("/api/user/tasks", json={
            "title": "Alice Unique Name Task",
            "workspace": "Alice Unique Lab"
        }, cookies={"session_id": self.sess_a})
        self.assertEqual(res_name.status_code, 200)
        name_id = res_name.json()["id"]
        name_row = self.cursor.execute("SELECT workspace FROM user_tasks WHERE id = ?", (name_id,)).fetchone()
        self.assertEqual(name_row["workspace"], ws_alice_valid)


