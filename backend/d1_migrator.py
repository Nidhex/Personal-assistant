import sqlite3
import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

EXPECTED_TABLES = [
    "users",
    "sessions",
    "oauth_states",
    "user_tokens",
    "user_tasks",
    "user_workspaces",
    "user_approvals",
    "user_activity",
    "conversations",
    "messages",
    "user_workspace_notes",
    "user_calendar_events",
    "user_study_materials",
    "user_revision_plans",
    "user_agent_settings",
    "agent_runs",
    "agent_run_steps",
    "daily_digests"
]

def verify_schema_integrity(conn: Any) -> Dict[str, Any]:
    """
    Verifies that all 18 expected application tables exist and have valid structure.
    Works with standard sqlite3.Connection and D1 adapters.
    """
    cursor = conn.cursor() if hasattr(conn, "cursor") else conn
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    rows = cursor.fetchall()
    
    # Handle both tuple/sqlite3.Row and dict objects
    existing_tables = set()
    for row in rows:
        if isinstance(row, dict):
            existing_tables.add(row.get("name"))
        elif hasattr(row, "keys"):
            existing_tables.add(row["name"])
        else:
            existing_tables.add(row[0])

    missing = [t for t in EXPECTED_TABLES if t not in existing_tables]
    
    table_columns = {}
    for table in EXPECTED_TABLES:
        if table in existing_tables:
            cursor.execute(f"PRAGMA table_info({table});")
            col_rows = cursor.fetchall()
            cols = []
            for col in col_rows:
                if isinstance(col, dict):
                    cols.append(col.get("name"))
                elif hasattr(col, "keys"):
                    cols.append(col["name"])
                else:
                    cols.append(col[1])
            table_columns[table] = cols

    return {
        "valid": len(missing) == 0,
        "total_expected": len(EXPECTED_TABLES),
        "total_found": len(existing_tables),
        "existing_tables": sorted(list(existing_tables)),
        "missing_tables": missing,
        "table_columns": table_columns
    }

def export_sqlite_to_d1_sql(sqlite_path: str, output_sql_path: Optional[str] = None) -> str:
    """
    Safely exports table data from local SQLite database into D1-compatible SQL statements.
    Opens local SQLite strictly in read-only URI mode to guarantee zero modification of source.
    """
    abs_path = os.path.abspath(sqlite_path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"Source SQLite database not found at {abs_path}")

    # Read-only URI connection ensures source database cannot be modified
    uri = f"file:{abs_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    sql_lines = [
        "-- Cloudflare D1 Data Export",
        "-- Auto-generated from local SQLite (Read-Only Mode)",
        "PRAGMA foreign_keys = OFF;"
    ]

    for table in EXPECTED_TABLES:
        try:
            cursor.execute(f"SELECT * FROM {table};")
            rows = cursor.fetchall()
            if not rows:
                continue

            sql_lines.append(f"\n-- Data for table: {table}")
            for row in rows:
                keys = list(row.keys())
                cols_str = ", ".join(f'"{k}"' for k in keys)
                vals = []
                for k in keys:
                    v = row[k]
                    if v is None:
                        vals.append("NULL")
                    elif isinstance(v, (int, float)):
                        vals.append(str(v))
                    else:
                        # Escape single quotes for SQL string literal
                        escaped = str(v).replace("'", "''")
                        vals.append(f"'{escaped}'")
                vals_str = ", ".join(vals)
                sql_lines.append(f"INSERT OR REPLACE INTO {table} ({cols_str}) VALUES ({vals_str});")
        except sqlite3.OperationalError:
            # Table might not exist yet in an uninitialized source
            continue

    sql_lines.append("\nPRAGMA foreign_keys = ON;\n")
    conn.close()

    full_sql = "\n".join(sql_lines)
    if output_sql_path:
        out_abs = os.path.abspath(output_sql_path)
        os.makedirs(os.path.dirname(out_abs), exist_ok=True)
        with open(out_abs, "w", encoding="utf-8") as f:
            f.write(full_sql)

    return full_sql

def apply_migration_script(conn: Any, script_path: str, is_production_or_default_sqlite: bool = False):
    """
    Executes a SQL migration script against the provided connection or adapter.
    Enforces rule: Never execute destructive rollback scripts against the default/active database.
    """
    abs_path = os.path.abspath(script_path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"Migration script not found at {abs_path}")

    with open(abs_path, "r", encoding="utf-8") as f:
        sql = f.read()

    if is_production_or_default_sqlite and "DROP TABLE" in sql.upper():
        raise PermissionError("Safety gate: Destructive scripts (DROP TABLE) cannot be executed against active/default database.")

    if hasattr(conn, "executescript"):
        conn.executescript(sql)
    else:
        # Split by semicolon for statement-by-statement execution
        statements = [stmt.strip() for stmt in sql.split(";") if stmt.strip()]
        for stmt in statements:
            conn.execute(stmt)
