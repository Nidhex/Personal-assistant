import os
import re
import json
import time
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from zoneinfo import ZoneInfo

from .database import get_db
from .google_service import fetch_gmail_messages
from .agent import detect_calendar_conflicts, parse_relative_date, parse_time_to_minutes

# Active run locks in memory to prevent concurrent / overlapping runs per user
_ACTIVE_USER_RUNS = set()

class SettingsDict(dict):
    """
    Dictionary subclass with async __await__ support that enables transparent
    access in both synchronous SQLite workflows and asynchronous Cloudflare D1 workflows.
    """
    def __init__(self, data=None, coro=None):
        if data:
            super().__init__(data)
        self._coro = coro

    async def _resolve(self):
        if self._coro is not None:
            res = await self._coro
            self.update(res)
            self._coro = None
        return self

    def __await__(self):
        return self._resolve().__await__()

# -------------------------------------------------------------
# 1. USER SETTINGS & PREFERENCES MANAGEMENT
# -------------------------------------------------------------
def get_or_create_user_settings(user_id: str) -> SettingsDict:
    """Retrieves user agent settings. If none exist, initializes safe opt-in defaults."""
    conn = get_db()
    cursor = conn.cursor()

    # Cloudflare Python Worker async D1 mode
    if getattr(conn, "worker_env", None) and hasattr(conn.worker_env, "DB"):
        async def _fetch_d1():
            await cursor.execute("""
                SELECT user_id, daily_run_enabled, preferred_time, timezone, permitted_sources,
                       max_duration_seconds, max_tool_steps, kill_switch_enabled,
                       next_run_at, last_run_at, last_run_status, updated_at
                FROM user_agent_settings WHERE user_id = ?
            """, (user_id,))
            row = cursor.fetchone()

            if not row:
                now_str = datetime.now(timezone.utc).isoformat()
                default_next = calculate_next_run("08:00", "UTC")
                await cursor.execute("""
                    INSERT INTO user_agent_settings (
                        user_id, daily_run_enabled, preferred_time, timezone, permitted_sources,
                        max_duration_seconds, max_tool_steps, kill_switch_enabled,
                        next_run_at, last_run_at, last_run_status, updated_at
                    ) VALUES (?, 0, '08:00', 'UTC', '["gmail","tasks","calendar"]', 120, 10, 0, ?, NULL, 'never_run', ?)
                    ON CONFLICT(user_id) DO NOTHING
                """, (user_id, default_next, now_str))
                await cursor.execute("SELECT * FROM user_agent_settings WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()

            if not row:
                return {
                    "user_id": user_id, "daily_run_enabled": 0, "preferred_time": "08:00",
                    "timezone": "UTC", "permitted_sources": ["gmail", "tasks", "calendar"],
                    "max_duration_seconds": 120, "max_tool_steps": 10, "kill_switch_enabled": 0,
                    "next_run_at": None, "last_run_at": None, "last_run_status": "never_run"
                }

            d = dict(row)
            try:
                d["permitted_sources"] = json.loads(d["permitted_sources"])
            except Exception:
                d["permitted_sources"] = ["gmail", "tasks", "calendar"]
            return d

        return SettingsDict(coro=_fetch_d1())

    # Synchronous SQLite mode
    cursor.execute("""
        SELECT user_id, daily_run_enabled, preferred_time, timezone, permitted_sources,
               max_duration_seconds, max_tool_steps, kill_switch_enabled,
               next_run_at, last_run_at, last_run_status, updated_at
        FROM user_agent_settings WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()

    if not row:
        now_str = datetime.now(timezone.utc).isoformat()
        default_next = calculate_next_run("08:00", "UTC")
        cursor.execute("""
            INSERT INTO user_agent_settings (
                user_id, daily_run_enabled, preferred_time, timezone, permitted_sources,
                max_duration_seconds, max_tool_steps, kill_switch_enabled,
                next_run_at, last_run_at, last_run_status, updated_at
            ) VALUES (?, 0, '08:00', 'UTC', '["gmail","tasks","calendar"]', 120, 10, 0, ?, NULL, 'never_run', ?)
            ON CONFLICT(user_id) DO NOTHING
        """, (user_id, default_next, now_str))
        if hasattr(conn, "commit"):
            conn.commit()
        cursor.execute("SELECT * FROM user_agent_settings WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()

    if hasattr(conn, "close"):
        conn.close()

    if not row:
        return SettingsDict({
            "user_id": user_id, "daily_run_enabled": 0, "preferred_time": "08:00",
            "timezone": "UTC", "permitted_sources": ["gmail", "tasks", "calendar"],
            "max_duration_seconds": 120, "max_tool_steps": 10, "kill_switch_enabled": 0,
            "next_run_at": None, "last_run_at": None, "last_run_status": "never_run"
        })

    d = dict(row)
    try:
        d["permitted_sources"] = json.loads(d["permitted_sources"])
    except Exception:
        d["permitted_sources"] = ["gmail", "tasks", "calendar"]
    return SettingsDict(d)

def update_user_settings(user_id: str, settings: Dict[str, Any]) -> SettingsDict:
    """Updates user agent settings with validation."""
    conn = get_db()
    cursor = conn.cursor()

    if getattr(conn, "worker_env", None) and hasattr(conn.worker_env, "DB"):
        async def _update_d1():
            current = await get_or_create_user_settings(user_id)
            enabled = int(bool(settings.get("daily_run_enabled", current.get("daily_run_enabled", 0))))
            pref_time = settings.get("preferred_time", current.get("preferred_time", "08:00"))
            tz_str = settings.get("timezone", current.get("timezone", "UTC"))
            try:
                ZoneInfo(tz_str)
            except Exception:
                tz_str = "UTC"
            if not re.match(r"^\d{1,2}:\d{2}$", pref_time):
                pref_time = "08:00"
            sources = settings.get("permitted_sources", current.get("permitted_sources", ["gmail", "tasks", "calendar"]))
            sources_json = json.dumps(sources) if isinstance(sources, list) else json.dumps(["gmail", "tasks", "calendar"])
            kill_switch = int(bool(settings.get("kill_switch_enabled", current.get("kill_switch_enabled", 0))))
            next_run = calculate_next_run(pref_time, tz_str) if enabled else None
            now_str = datetime.now(timezone.utc).isoformat()

            await cursor.execute("""
                UPDATE user_agent_settings
                SET daily_run_enabled = ?, preferred_time = ?, timezone = ?,
                    permitted_sources = ?, kill_switch_enabled = ?,
                    next_run_at = ?, updated_at = ?
                WHERE user_id = ?
            """, (enabled, pref_time, tz_str, sources_json, kill_switch, next_run, now_str, user_id))
            return await get_or_create_user_settings(user_id)

        return SettingsDict(coro=_update_d1())

    current = get_or_create_user_settings(user_id)
    enabled = int(bool(settings.get("daily_run_enabled", current["daily_run_enabled"])))
    pref_time = settings.get("preferred_time", current["preferred_time"])
    tz_str = settings.get("timezone", current["timezone"])
    
    # Validate timezone
    try:
        ZoneInfo(tz_str)
    except Exception:
        tz_str = "UTC"

    # Validate preferred time format (HH:MM)
    if not re.match(r"^\d{1,2}:\d{2}$", pref_time):
        pref_time = "08:00"

    sources = settings.get("permitted_sources", current["permitted_sources"])
    sources_json = json.dumps(sources) if isinstance(sources, list) else json.dumps(["gmail", "tasks", "calendar"])

    kill_switch = int(bool(settings.get("kill_switch_enabled", current["kill_switch_enabled"])))
    next_run = calculate_next_run(pref_time, tz_str) if enabled else None
    now_str = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
        UPDATE user_agent_settings
        SET daily_run_enabled = ?, preferred_time = ?, timezone = ?,
            permitted_sources = ?, kill_switch_enabled = ?,
            next_run_at = ?, updated_at = ?
        WHERE user_id = ?
    """, (enabled, pref_time, tz_str, sources_json, kill_switch, next_run, now_str, user_id))
    if hasattr(conn, "commit"):
        conn.commit()
    if hasattr(conn, "close"):
        conn.close()

    return get_or_create_user_settings(user_id)

def calculate_next_run(preferred_time: str, tz_name: str) -> str:
    """Calculates ISO timestamp of next scheduled run in user's timezone."""
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")

    now_local = datetime.now(tz)
    parts = preferred_time.split(":")
    target_hour = int(parts[0])
    target_min = int(parts[1])

    scheduled_today = now_local.replace(hour=target_hour, minute=target_min, second=0, microsecond=0)
    if scheduled_today <= now_local:
        scheduled_next = scheduled_today + timedelta(days=1)
    else:
        scheduled_next = scheduled_today

    return scheduled_next.astimezone(timezone.utc).isoformat()

# -------------------------------------------------------------
# 2. RUN STEP LOGGING HELPER
# -------------------------------------------------------------
def log_run_step(
    run_id: str,
    user_id: str,
    step_number: int,
    step_name: str,
    tool_name: Optional[str],
    policy_decision: str,
    status: str,
    result: str,
    tool_parameters: Optional[Dict[str, Any]] = None,
    approval_required: bool = False,
    latency_ms: str = "0ms"
):
    """Appends an immutable audit step to agent_run_steps and user_activity."""
    step_id = f"step_{int(time.time()*1000)}_{os.urandom(2).hex()}"
    now_str = datetime.now(timezone.utc).isoformat()
    params_str = json.dumps(tool_parameters) if tool_parameters else None

    import logging
    import sqlite3
    import uuid
    logger = logging.getLogger(__name__)

    conn = get_db()
    if isinstance(conn, sqlite3.Connection):
        conn.execute("PRAGMA busy_timeout = 1500")
    try:
        conn.execute("""
            INSERT INTO agent_run_steps (
                id, run_id, user_id, step_number, step_name, tool_name,
                tool_parameters, policy_decision, approval_required, status, result, latency_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            step_id, run_id, user_id, step_number, step_name, tool_name,
            params_str, policy_decision, int(approval_required), status, result, latency_ms, now_str
        ))

        # Also log into user_activity for unified trace visibility
        conn.execute("""
            INSERT INTO user_activity (id, user_id, trigger, status, latency, result, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (f"act_{uuid.uuid4().hex}", user_id, f"Agent Step {step_number}: {step_name}", status.capitalize(), latency_ms, result[:200], now_str))

        conn.commit()
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.warning(
            "log_run_step failed (run_id=%s, user_id=%s, step=%s): %s",
            run_id, user_id, step_number, exc,
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass

def extract_deadline_from_text(text: str):
    """Safely extracts deadline indicators from untrusted email text without executing commands."""
    lower = text.lower()
    has_deadline = any(k in lower for k in ["deadline", "due", "submit", "assignment", "by tomorrow", "by friday", "meeting at", "urgent"])
    dt = "Tomorrow" if "tomorrow" in lower else ("Friday" if "friday" in lower else "Upcoming")
    action = "Task created from email deadline" if has_deadline else None
    return has_deadline, dt, action

# -------------------------------------------------------------
# 3. DAILY RUN ORCHESTRATOR
# -------------------------------------------------------------
async def execute_daily_run(user_id: str, trigger_type: str = "manual") -> Dict[str, Any]:
    """
    Executes unattended daily agent run sequence:
    1. Check overlap lock.
    2. Create run record.
    3. Check kill switch (pre-execution).
    4. Read authorized Gmail & extract deadlines (untrusted data protection).
    5. Retrieve tasks and calendar data.
    6. Run policy gate on each action (create permitted tasks, stage outbound drafts).
    7. Generate structured Daily Digest.
    8. Record complete step audit.
    """
    # Overlapping run prevention
    if user_id in _ACTIVE_USER_RUNS:
        return {
            "success": False,
            "status": "already_running",
            "message": "An agent run is currently in progress for this user."
        }

    _ACTIVE_USER_RUNS.add(user_id)
    start_time = time.time()
    run_id = f"run_{int(time.time()*1000)}_{os.urandom(2).hex()}"
    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.isoformat()

    conn = get_db()
    conn.execute("""
        INSERT INTO agent_runs (
            id, user_id, trigger_type, status, started_at, total_steps,
            actions_completed, actions_refused, actions_failed, summary
        ) VALUES (?, ?, ?, 'running', ?, 0, 0, 0, 0, 'Run in progress')
    """, (run_id, user_id, trigger_type, now_str))
    conn.commit()
    conn.close()

    step_num = 1
    actions_completed = 0
    actions_refused = 0
    actions_failed = 0
    warnings = []
    created_tasks = []
    staged_approvals = []
    important_emails = []

    try:
        # Step 1: Load configuration & permissions
        settings = get_or_create_user_settings(user_id)
        permitted_sources = settings.get("permitted_sources", ["gmail", "tasks", "calendar"])
        kill_switch = bool(settings.get("kill_switch_enabled", False))

        log_run_step(
            run_id, user_id, step_num, "Load User Settings & Permissions",
            None, "Allowed", "completed",
            f"Loaded preferences (Daily enabled: {settings['daily_run_enabled']}, Sources: {permitted_sources})"
        )
        step_num += 1

        # Step 2: Emergency Kill Switch Pre-Check
        if kill_switch:
            log_run_step(
                run_id, user_id, step_num, "Emergency Kill Switch Verification",
                None, "Refused: Emergency Kill Switch Active", "blocked",
                "Agent run halted immediately prior to tool execution because the emergency kill switch is engaged."
            )
            actions_refused += 1

            conn = get_db()
            conn.execute("""
                UPDATE agent_runs
                SET status = 'stopped_by_kill_switch', completed_at = ?, total_steps = ?,
                    actions_refused = ?, summary = 'Halted immediately by emergency kill switch'
                WHERE id = ?
            """, (datetime.now(timezone.utc).isoformat(), step_num, actions_refused, run_id))
            conn.execute("UPDATE user_agent_settings SET last_run_at = ?, last_run_status = 'stopped_by_kill_switch' WHERE user_id = ?",
                         (datetime.now(timezone.utc).isoformat(), user_id))
            conn.commit()
            conn.close()

            return {
                "success": False,
                "run_id": run_id,
                "status": "stopped_by_kill_switch",
                "message": "Run stopped by emergency kill switch."
            }

        # Step 3: Read Authorized Gmail Data
        email_messages = []
        if "gmail" in permitted_sources:
            try:
                t0 = time.time()
                mail_data = await fetch_gmail_messages(user_id=user_id, max_results=12)
                email_messages = mail_data.get("messages", [])
                latency = f"{int((time.time() - t0)*1000)}ms"

                log_run_step(
                    run_id, user_id, step_num, "Read Authorized Gmail Inbox",
                    "read_gmail", "Allowed & Executed", "completed",
                    f"Retrieved {len(email_messages)} inbox messages from connected Gmail account.",
                    {"max_results": 12}, False, latency
                )
                actions_completed += 1
            except Exception as e:
                warnings.append(f"Gmail read unavailable: {str(e)}")
                log_run_step(
                    run_id, user_id, step_num, "Read Authorized Gmail Inbox",
                    "read_gmail", "Allowed", "completed",
                    f"Gmail account is not connected or read access returned: {str(e)}"
                )
        else:
            log_run_step(
                run_id, user_id, step_num, "Read Gmail Skipped",
                None, "Skipped", "completed", "Gmail source is not permitted in user agent settings."
            )
        step_num += 1

        # Step 4: Extract Deadlines & Evaluate Email Actions (Untrusted Content Sandbox)
        for msg in email_messages[:6]:
            subject = msg.get("subject", "")
            snippet = msg.get("snippet", "")
            full_text = f"{subject} {snippet}".lower()
            msg_id = msg.get("id")

            # Anti-prompt-injection: untrusted text is never executed as agent instructions
            has_deadline = any(k in full_text for k in ["deadline", "due", "submit", "assignment", "by tomorrow", "by friday", "meeting at", "urgent"])
            urgency = "high" if any(u in full_text for u in ["urgent", "action required", "asap", "immediate"]) else "normal"

            if has_deadline:
                important_emails.append({
                    "id": msg_id,
                    "sender": msg.get("senderName", "Unknown"),
                    "subject": subject,
                    "snippet": snippet[:100],
                    "urgency": urgency,
                    "deadline_detected": "Tomorrow" if "tomorrow" in full_text else "Upcoming",
                    "recommended_action": "Task created from email deadline"
                })

                # Check kill switch before creating each task
                curr_settings = get_or_create_user_settings(user_id)
                if curr_settings.get("kill_switch_enabled"):
                    warnings.append("Remaining email task creations halted by kill switch.")
                    break

                # Deduplicate: check if task with same source_email_id already exists
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("SELECT id, title FROM user_tasks WHERE user_id = ? AND source_email_id = ?", (user_id, msg_id))
                existing_t = cursor.fetchone()

                if not existing_t:
                    task_title = f"Review: {subject[:45]}"
                    due_date = parse_relative_date("tomorrow" if "tomorrow" in full_text else "today")
                    new_task_id = f"tsk_auto_{int(time.time()*1000)}_{os.urandom(2).hex()}"

                    cursor.execute("""
                        INSERT INTO user_tasks (id, user_id, title, source, source_email_id, due_date, priority, completed, workspace, created_at)
                        VALUES (?, ?, ?, 'Daily Agent Run', ?, ?, ?, 0, 'General', ?)
                    """, (new_task_id, user_id, task_title, msg_id, due_date, urgency, datetime.now(timezone.utc).isoformat()))
                    conn.commit()

                    created_tasks.append(f"{task_title} (Due: {due_date})")
                    actions_completed += 1

                    log_run_step(
                        run_id, user_id, step_num, f"Create Task from Email: {task_title}",
                        "create_task", "Allowed & Executed", "completed",
                        f"Created internal task '{task_title}' (Due: {due_date}, Source Email: {msg_id})",
                        {"title": task_title, "due_date": due_date, "source_email_id": msg_id}
                    )
                    step_num += 1
                conn.close()

            # If email requests an explicit reply/action: stage outbound draft for HUMAN APPROVAL
            if "please reply" in full_text or "need your response" in full_text or "rsvp" in full_text:
                curr_settings = get_or_create_user_settings(user_id)
                if not curr_settings.get("kill_switch_enabled"):
                    appr_id = f"appr_auto_{int(time.time()*1000)}_{os.urandom(2).hex()}"
                    draft_body = f"Hello {msg.get('senderName', '')},\n\nI have received your email regarding '{subject}'. I am reviewing it and will follow up shortly.\n\nBest regards,\n{msg.get('senderName', 'User')}"

                    conn = get_db()
                    try:
                        cursor = conn.cursor()
                        # Check duplicate approval
                        cursor.execute("SELECT id FROM user_approvals WHERE user_id = ? AND subject LIKE ? AND status = 'pending'", (user_id, f"%{subject[:30]}%"))
                        if not cursor.fetchone():
                            cursor.execute("""
                                INSERT INTO user_approvals (id, user_id, type, target, subject, reason, risk_level, draft_content, status, created_at)
                                VALUES (?, ?, 'Email Draft', ?, ?, ?, 'Medium', ?, 'pending', ?)
                            """, (
                                appr_id, user_id, msg.get("senderEmail", "sender@domain.com"),
                                f"Re: {subject}", "Daily agent formulated reply; requires human review before dispatch.",
                                draft_body, datetime.now(timezone.utc).isoformat()
                            ))
                            conn.commit()
                            staged_approvals.append(f"Re: {subject} (To: {msg.get('senderName', 'Sender')})")
                            actions_completed += 1

                            log_run_step(
                                run_id, user_id, step_num, f"Stage Draft Reply: {subject[:30]}",
                                "propose_draft", "Queued for Human Approval", "completed",
                                f"Staged outbound email draft in user_approvals (ID: {appr_id}). Action remains paused until approved.",
                                {"subject": f"Re: {subject}", "target": msg.get("senderEmail", "")},
                                approval_required=True
                            )
                            step_num += 1
                    finally:
                        conn.close()

        # Step 5: Read Tasks & Calendar Events
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, due_date, priority, completed, workspace FROM user_tasks WHERE user_id = ?", (user_id,))
        all_tasks = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT id, title, event_date, start_time, end_time, category FROM user_calendar_events WHERE user_id = ? ORDER BY event_date ASC", (user_id,))
        all_cal_events = [dict(r) for r in cursor.fetchall()]
        conn.close()

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        due_today = [t for t in all_tasks if (t.get("due_date") == today_str or t.get("due_date") == "Today") and not t.get("completed")]
        overdue = [t for t in all_tasks if t.get("due_date") and t.get("due_date") < today_str and t.get("due_date") not in ["Today", "No due date"] and not t.get("completed")]
        upcoming = [t for t in all_tasks if t.get("due_date") and t.get("due_date") > today_str and not t.get("completed")]
        completed_tasks = [t for t in all_tasks if t.get("completed")]

        today_events = [e for e in all_cal_events if e.get("event_date") == today_str]
        upcoming_events = [e for e in all_cal_events if e.get("event_date") and e.get("event_date") > today_str]

        # Calendar conflict inspection
        detected_conflicts = []
        for e in today_events:
            conflicts = detect_calendar_conflicts(user_id, e["event_date"], e["start_time"], e["end_time"], exclude_event_id=e["id"])
            if conflicts:
                detected_conflicts.append(f"Overlap between '{e['title']}' and '{conflicts[0]['title']}' on {e['event_date']}")

        log_run_step(
            run_id, user_id, step_num, "Retrieve Tasks & Calendar Schedule",
            "list_tasks", "Allowed & Executed", "completed",
            f"Audited {len(all_tasks)} tasks ({len(due_today)} due today, {len(overdue)} overdue) and {len(all_cal_events)} calendar events."
        )
        step_num += 1

        # Step 6: Query Pending Approvals
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, type, target, subject, reason, risk_level, draft_content, created_at FROM user_approvals WHERE user_id = ? AND status = 'pending'", (user_id,))
        pending_approvals = [dict(r) for r in cursor.fetchall()]
        conn.close()

        # Step 7: Construct Structured Daily Digest
        cutoff_12h = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
        needs_your_approval = [
            a for a in pending_approvals
            if (a.get("created_at") or "") <= cutoff_12h
        ]
        digest_data = {
            "digest_date": today_str,
            "run_id": run_id,
            "trigger_type": trigger_type,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "important_emails": important_emails,
            "tasks": {
                "due_today": due_today,
                "overdue": overdue,
                "upcoming": upcoming[:5],
                "newly_created": created_tasks,
                "completed_count": len(completed_tasks)
            },
            "calendar": {
                "today_events": today_events,
                "upcoming_events": upcoming_events[:5],
                "conflicts": detected_conflicts,
                "app_calendar_events": len(all_cal_events)
            },
            "pending_approvals": pending_approvals,
            "needs_your_approval": needs_your_approval,
            "agent_activity": {
                "actions_completed": actions_completed,
                "actions_refused": actions_refused,
                "actions_failed": actions_failed,
                "attention_items": [
                    f"{len(due_today)} task(s) due today",
                    f"{len(overdue)} task(s) overdue" if overdue else "No overdue tasks",
                    f"{len(pending_approvals)} action(s) awaiting approval in queue" if pending_approvals else "No pending approvals",
                    f"{len(detected_conflicts)} calendar conflict(s) detected" if detected_conflicts else "No calendar conflicts"
                ]
            }
        }

        digest_id = f"dig_{int(time.time()*1000)}_{os.urandom(2).hex()}"
        conn = get_db()
        conn.execute("""
            INSERT INTO daily_digests (id, user_id, run_id, digest_date, title, content_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            digest_id, user_id, run_id, today_str,
            f"Daily Briefing — {datetime.now(timezone.utc).strftime('%B %d, %Y')}",
            json.dumps(digest_data), datetime.now(timezone.utc).isoformat()
        ))

        # Step 8: Finalize Run Record
        run_status = "completed_with_warnings" if warnings else "completed"
        summary_text = f"Finished run in {int((time.time() - start_time)*1000)}ms. {actions_completed} actions executed, {len(created_tasks)} tasks created, {len(staged_approvals)} drafts staged."

        conn.execute("""
            UPDATE agent_runs
            SET status = ?, completed_at = ?, total_steps = ?,
                actions_completed = ?, actions_refused = ?, actions_failed = ?,
                summary = ?, error_message = ?
            WHERE id = ?
        """, (
            run_status, datetime.now(timezone.utc).isoformat(), step_num,
            actions_completed, actions_refused, actions_failed,
            summary_text, "; ".join(warnings) if warnings else None, run_id
        ))

        # Update next run timestamp for user
        next_run = calculate_next_run(settings.get("preferred_time", "08:00"), settings.get("timezone", "UTC"))
        conn.execute("""
            UPDATE user_agent_settings
            SET last_run_at = ?, last_run_status = ?, next_run_at = ?, updated_at = ?
            WHERE user_id = ?
        """, (datetime.now(timezone.utc).isoformat(), run_status, next_run, datetime.now(timezone.utc).isoformat(), user_id))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "run_id": run_id,
            "status": run_status,
            "summary": summary_text,
            "digest": digest_data
        }

    except Exception as e:
        import logging
        import sqlite3
        logger = logging.getLogger(__name__)
        actions_failed += 1
        err_msg = str(e)
        conn = get_db()
        if isinstance(conn, sqlite3.Connection):
            conn.execute("PRAGMA busy_timeout = 1500")
        try:
            conn.execute("""
                UPDATE agent_runs
                SET status = 'failed', completed_at = ?, total_steps = ?,
                    actions_failed = ?, error_message = ?
                WHERE id = ?
            """, (datetime.now(timezone.utc).isoformat(), step_num, actions_failed, err_msg, run_id))
            conn.execute("UPDATE user_agent_settings SET last_run_at = ?, last_run_status = 'failed' WHERE user_id = ?",
                         (datetime.now(timezone.utc).isoformat(), user_id))
            conn.commit()
        except Exception as rec_exc:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.warning(
                "Failed to record run failure (run_id=%s, original_error=%s): %s",
                run_id, err_msg, rec_exc,
            )
        finally:
            try:
                conn.close()
            except Exception:
                pass

        return {
            "success": False,
            "run_id": run_id,
            "status": "failed",
            "error": err_msg
        }

    finally:
        _ACTIVE_USER_RUNS.discard(user_id)
