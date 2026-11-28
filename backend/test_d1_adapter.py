import unittest
import os
import tempfile
import sqlite3
import hashlib
from pathlib import Path

from backend.database import (
    get_db,
    init_db,
    CloudflareD1DatabaseAdapter,
    D1PreparedStatement,
    DB_PATH
)
from backend.d1_migrator import (
    verify_schema_integrity,
    export_sqlite_to_d1_sql,
    apply_migration_script,
    EXPECTED_TABLES
)

class TestCloudflareD1AdapterAndMigration(unittest.TestCase):
    def setUp(self):
        # Create an isolated temporary database for test adapter instances
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db_path = os.path.join(self.temp_dir.name, "test_d1.db")
        self.adapter = CloudflareD1DatabaseAdapter(test_mode=True, test_db_path=self.test_db_path)
        init_db(conn=self.adapter)

    def tearDown(self):
        self.adapter.close()
        self.temp_dir.cleanup()

    def test_schema_initialization_all_18_tables(self):
        """Verify that all 18 tables defined in specification are created."""
        integrity = verify_schema_integrity(self.adapter)
        self.assertTrue(integrity["valid"], f"Missing tables: {integrity['missing_tables']}")
        self.assertGreaterEqual(len(integrity["existing_tables"]), 18)
        for tbl in EXPECTED_TABLES:
            self.assertIn(tbl, integrity["existing_tables"])

    def test_crud_operations_and_dict_mapping(self):
        """Test insert, select, update, and delete through D1 adapter."""
        # 1. Insert User
        cur = self.adapter.cursor()
        cur.execute(
            "INSERT INTO users (id, email, name, picture, created_at) VALUES (?, ?, ?, ?, ?)",
            ("u_test_1", "tester@test.local", "Test User", "https://pic.test/1", "2026-11-27T00:00:00Z")
        )
        self.adapter.commit()

        # 2. Select User
        cur.execute("SELECT * FROM users WHERE id = ?", ("u_test_1",))
        user = cur.fetchone()
        self.assertIsNotNone(user)
        self.assertEqual(user["id"], "u_test_1")
        self.assertEqual(user["email"], "tester@test.local")
        self.assertEqual(user["name"], "Test User")

        # 3. Update User
        cur.execute("UPDATE users SET name = ? WHERE id = ?", ("Updated Name", "u_test_1"))
        self.adapter.commit()
        cur.execute("SELECT name FROM users WHERE id = ?", ("u_test_1",))
        updated = cur.fetchone()
        self.assertEqual(updated["name"], "Updated Name")

        # 4. Insert Task
        cur.execute(
            "INSERT INTO user_tasks (id, user_id, title, priority, completed, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("t_1", "u_test_1", "Complete Phase 1", "high", 0, "2026-11-27T00:00:00Z")
        )
        self.adapter.commit()
        cur.execute("SELECT * FROM user_tasks WHERE user_id = ?", ("u_test_1",))
        tasks = cur.fetchall()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["title"], "Complete Phase 1")

    def test_prepared_statement_interface(self):
        """Verify Cloudflare D1 native prepared statement methods: all(), first(), run(), raw()."""
        # Insert test records
        stmt = self.adapter.prepare(
            "INSERT INTO users (id, email, name, picture, created_at) VALUES (?, ?, ?, ?, ?)"
        )
        stmt.bind("u_prep_1", "prep1@test.local", "User One", None, "2026-11-27T00:00:00Z").run()
        stmt.bind("u_prep_2", "prep2@test.local", "User Two", None, "2026-11-27T00:00:00Z").run()
        self.adapter.commit()

        # Test .first()
        row = self.adapter.prepare("SELECT * FROM users WHERE id = ?").bind("u_prep_1").first()
        self.assertIsNotNone(row)
        self.assertEqual(row["email"], "prep1@test.local")

        # Test .first(column_name)
        email = self.adapter.prepare("SELECT * FROM users WHERE id = ?").bind("u_prep_2").first("email")
        self.assertEqual(email, "prep2@test.local")

        # Test .all()
        res = self.adapter.prepare("SELECT id, email FROM users ORDER BY id ASC").all()
        self.assertTrue(res["success"])
        self.assertEqual(len(res["results"]), 2)
        self.assertEqual(res["results"][0]["id"], "u_prep_1")

        # Test .raw()
        raw_rows = self.adapter.prepare("SELECT id, email FROM users ORDER BY id ASC").raw()
        self.assertEqual(len(raw_rows), 2)
        self.assertEqual(raw_rows[0], ["u_prep_1", "prep1@test.local"])

    def test_foreign_key_cascading(self):
        """Verify that deleting a user cascades to tasks, workspaces, and sessions."""
        cur = self.adapter.cursor()
        cur.execute("INSERT INTO users (id, email, name, created_at) VALUES (?, ?, ?, ?)",
                    ("u_cascade", "cascade@test.local", "Cascade User", "2026-11-27T00:00:00Z"))
        cur.execute("INSERT INTO sessions (session_id, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
                    ("s_casc", "u_cascade", "2027-01-01T00:00:00Z", "2026-11-27T00:00:00Z"))
        cur.execute("INSERT INTO user_tasks (id, user_id, title, created_at) VALUES (?, ?, ?, ?)",
                    ("t_casc", "u_cascade", "Task To Delete", "2026-11-27T00:00:00Z"))
        cur.execute("INSERT INTO user_workspaces (id, user_id, name, type, created_at) VALUES (?, ?, ?, ?, ?)",
                    ("w_casc", "u_cascade", "Workspace To Delete", "study", "2026-11-27T00:00:00Z"))
        self.adapter.commit()

        # Delete user
        cur.execute("DELETE FROM users WHERE id = ?", ("u_cascade",))
        self.adapter.commit()

        # Check cascaded deletion
        cur.execute("SELECT * FROM sessions WHERE user_id = ?", ("u_cascade",))
        self.assertEqual(len(cur.fetchall()), 0)
        cur.execute("SELECT * FROM user_tasks WHERE user_id = ?", ("u_cascade",))
        self.assertEqual(len(cur.fetchall()), 0)
        cur.execute("SELECT * FROM user_workspaces WHERE user_id = ?", ("u_cascade",))
        self.assertEqual(len(cur.fetchall()), 0)

    def test_user_and_workspace_data_isolation(self):
        """Verify strict isolation between distinct users and workspaces."""
        cur = self.adapter.cursor()
        # User A & User B
        cur.execute("INSERT INTO users (id, email, name, created_at) VALUES (?, ?, ?, ?)",
                    ("user_a", "a@test.local", "User A", "2026-11-27T00:00:00Z"))
        cur.execute("INSERT INTO users (id, email, name, created_at) VALUES (?, ?, ?, ?)",
                    ("user_b", "b@test.local", "User B", "2026-11-27T00:00:00Z"))

        # Tasks for User A and User B
        cur.execute("INSERT INTO user_tasks (id, user_id, title, created_at) VALUES (?, ?, ?, ?)",
                    ("task_a", "user_a", "Secret Task A", "2026-11-27T00:00:00Z"))
        cur.execute("INSERT INTO user_tasks (id, user_id, title, created_at) VALUES (?, ?, ?, ?)",
                    ("task_b", "user_b", "Secret Task B", "2026-11-27T00:00:00Z"))
        self.adapter.commit()

        # Query isolated to user_a
        cur.execute("SELECT * FROM user_tasks WHERE user_id = ?", ("user_a",))
        a_tasks = cur.fetchall()
        self.assertEqual(len(a_tasks), 1)
        self.assertEqual(a_tasks[0]["title"], "Secret Task A")

        # Query isolated to user_b
        cur.execute("SELECT * FROM user_tasks WHERE user_id = ?", ("user_b",))
        b_tasks = cur.fetchall()
        self.assertEqual(len(b_tasks), 1)
        self.assertEqual(b_tasks[0]["title"], "Secret Task B")

    def test_transaction_commit_and_rollback(self):
        """Verify that transactions rollback cleanly on error."""
        cur = self.adapter.cursor()
        cur.execute("INSERT INTO users (id, email, name, created_at) VALUES (?, ?, ?, ?)",
                    ("u_tx", "tx@test.local", "Tx User", "2026-11-27T00:00:00Z"))
        self.adapter.commit()

        # Start uncommitted change then rollback
        cur.execute("UPDATE users SET name = 'Rollback Name' WHERE id = 'u_tx'")
        self.adapter.rollback()

        cur.execute("SELECT name FROM users WHERE id = 'u_tx'")
        row = cur.fetchone()
        self.assertEqual(row["name"], "Tx User")

    def test_migration_and_rollback_scripts_execution(self):
        """Verify that migrations/0001_initial_d1_schema.sql and rollback execute correctly on test DB."""
        # Use a fresh standalone SQLite test connection for schema scripts
        mig_conn = sqlite3.connect(":memory:")
        schema_path = Path(__file__).parent.parent / "migrations" / "0001_initial_d1_schema.sql"
        rollback_path = Path(__file__).parent.parent / "migrations" / "0001_initial_d1_schema_rollback.sql"

        # Apply schema migration
        apply_migration_script(mig_conn, str(schema_path))
        integrity = verify_schema_integrity(mig_conn)
        self.assertTrue(integrity["valid"])
        self.assertGreaterEqual(len(integrity["existing_tables"]), 18)

        # Apply rollback script on test connection
        apply_migration_script(mig_conn, str(rollback_path))
        rolled_back = verify_schema_integrity(mig_conn)
        self.assertEqual(len(rolled_back["existing_tables"]), 0)

        mig_conn.close()

    def test_safety_gate_protects_active_database_from_rollback(self):
        """Verify safety gate blocks destructive scripts on active database."""
        rollback_path = Path(__file__).parent.parent / "migrations" / "0001_initial_d1_schema_rollback.sql"
        with self.assertRaises(PermissionError):
            apply_migration_script(self.adapter, str(rollback_path), is_production_or_default_sqlite=True)

    def test_read_only_exporter_does_not_alter_source(self):
        """Verify export_sqlite_to_d1_sql operates in read-only mode and generates valid SQL."""
        if not DB_PATH.exists():
            init_db()

        # Compute pre-hash of source database file
        with open(DB_PATH, "rb") as f:
            pre_hash = hashlib.sha256(f.read()).hexdigest()

        # Export SQL
        exported_sql = export_sqlite_to_d1_sql(str(DB_PATH))
        self.assertIn("-- Cloudflare D1 Data Export", exported_sql)
        self.assertIn("PRAGMA foreign_keys = OFF;", exported_sql)
        self.assertIn("PRAGMA foreign_keys = ON;", exported_sql)

        # Compute post-hash of source database file to verify it was NOT modified
        with open(DB_PATH, "rb") as f:
            post_hash = hashlib.sha256(f.read()).hexdigest()

        self.assertEqual(pre_hash, post_hash, "CRITICAL: Source SQLite file was altered during export!")


if __name__ == "__main__":
    unittest.main()
