import asyncio
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, List

from .database import get_db
from .orchestrator import execute_daily_run, calculate_next_run, parse_and_validate_time

logger = logging.getLogger("scheduler")

def is_due_for_run(user_settings: Dict[str, Any], now_utc: Optional[datetime] = None) -> bool:
    """
    Determines whether a user is currently due for a scheduled daily run:
    1. Opt-in verification: daily_run_enabled == 1.
    2. Timezone localization: converts current UTC to user's configured timezone.
    3. Execution time check: current local time has reached or passed preferred_time.
    4. Exact-once daily deduplication: user has not already executed on today's local calendar date.
    5. Concurrent execution protection: no active run locked within last 10 minutes.
    """
    if not bool(user_settings.get("daily_run_enabled")):
        return False

    tz_str = user_settings.get("timezone", "UTC")
    try:
        user_tz = ZoneInfo(tz_str)
    except Exception:
        user_tz = ZoneInfo("UTC")

    now_utc = now_utc or datetime.now(timezone.utc)
    now_local = now_utc.astimezone(user_tz)
    today_str = now_local.strftime("%Y-%m-%d")

    pref_parsed = parse_and_validate_time(user_settings.get("preferred_time"))
    if pref_parsed is None:
        logger.warning(
            "Malformed preferred_time for user %s: %r. Skipping run safely.",
            user_settings.get("user_id"),
            user_settings.get("preferred_time")
        )
        return False

    pref_hour, pref_min = pref_parsed
    now_local_time = (now_local.hour, now_local.minute)

    # Has preferred time arrived today in user's timezone? (safe numerical comparison)
    if now_local_time < (pref_hour, pref_min):
        return False

    # Check if already executed on today's local date
    last_run_at = user_settings.get("last_run_at")
    if last_run_at:
        try:
            last_dt = datetime.fromisoformat(last_run_at)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            last_dt_local = last_dt.astimezone(user_tz)
            if last_dt_local.strftime("%Y-%m-%d") == today_str and user_settings.get("last_run_status") != "running":
                return False
        except Exception:
            pass

    # Check if currently locked / running within 10-minute timeout window
    last_status = user_settings.get("last_run_status")
    if last_status == "running" and last_run_at:
        try:
            last_dt = datetime.fromisoformat(last_run_at)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            if (now_utc - last_dt).total_seconds() < 600:
                # Active run is in progress
                return False
        except Exception:
            pass

    return True

def acquire_atomic_run_lock(conn: Any, user_id: str, now_utc: Optional[datetime] = None) -> bool:
    """
    Atomically acquires an execution claim in the database.
    Guarantees that multiple concurrent workers or overlapping triggers never execute
    the same user simultaneously, and prevents duplicate runs on the same calendar day.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()
    stale_threshold_iso = (now_utc - timedelta(minutes=10)).isoformat()

    cursor = conn.cursor() if hasattr(conn, "cursor") else conn

    # Retrieve current timezone and last run info
    cursor.execute("""
        SELECT timezone, last_run_at, last_run_status
        FROM user_agent_settings
        WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    if not row:
        return False

    row_dict = dict(row) if hasattr(row, "keys") else {
        "timezone": row[0], "last_run_at": row[1], "last_run_status": row[2]
    }
    tz_str = row_dict.get("timezone", "UTC")
    try:
        user_tz = ZoneInfo(tz_str)
    except Exception:
        user_tz = ZoneInfo("UTC")

    today_local = now_utc.astimezone(user_tz).strftime("%Y-%m-%d")

    # Pre-check: if already executed today in local timezone and not stale
    last_run_at = row_dict.get("last_run_at")
    if last_run_at:
        try:
            last_dt = datetime.fromisoformat(last_run_at)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            if last_dt.astimezone(user_tz).strftime("%Y-%m-%d") == today_local and row_dict.get("last_run_status") != "running":
                return False
        except Exception:
            pass

    # Atomic SQL Update Claim
    cursor.execute("""
        UPDATE user_agent_settings
        SET last_run_at = ?,
            last_run_status = 'running'
        WHERE user_id = ?
          AND daily_run_enabled = 1
          AND (
            last_run_status != 'running'
            OR last_run_at < ?
          )
    """, (now_iso, user_id, stale_threshold_iso))

    rowcount = cursor.rowcount if hasattr(cursor, "rowcount") else 0
    if hasattr(conn, "commit"):
        conn.commit()

    return rowcount > 0

def release_run_lock(conn: Any, user_id: str, status: str, next_run_at: Optional[str] = None):
    """
    Releases the database lock and updates final run status and next scheduled run timestamp.
    """
    cursor = conn.cursor() if hasattr(conn, "cursor") else conn
    if next_run_at:
        cursor.execute("""
            UPDATE user_agent_settings
            SET last_run_status = ?,
                next_run_at = ?
            WHERE user_id = ?
        """, (status, next_run_at, user_id))
    else:
        cursor.execute("""
            UPDATE user_agent_settings
            SET last_run_status = ?
            WHERE user_id = ?
        """, (status, user_id))

    if hasattr(conn, "commit"):
        conn.commit()

async def run_scheduled_tick(env: Optional[Any] = None, now_utc: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Evaluates and triggers daily agent runs across all eligible users.
    Called by Cloudflare Cron Triggers and local scheduler loop.
    Completely independent of HTTP request contexts.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    conn = get_db(worker_env=env)
    cursor = conn.cursor() if hasattr(conn, "cursor") else conn

    cursor.execute("""
        SELECT user_id, preferred_time, timezone, daily_run_enabled, last_run_at, last_run_status, kill_switch_enabled
        FROM user_agent_settings
        WHERE daily_run_enabled = 1
    """)
    rows = cursor.fetchall()
    users_to_check = []
    for r in rows:
        users_to_check.append(dict(r) if hasattr(r, "keys") else {
            "user_id": r[0], "preferred_time": r[1], "timezone": r[2],
            "daily_run_enabled": r[3], "last_run_at": r[4], "last_run_status": r[5],
            "kill_switch_enabled": r[6]
        })
    if hasattr(conn, "close"):
        conn.close()

    triggered = []
    skipped = []
    errors = []

    for u in users_to_check:
        user_id = u["user_id"]
        if not is_due_for_run(u, now_utc=now_utc):
            skipped.append({"user_id": user_id, "reason": "not_due_or_already_ran"})
            continue

        # Atomic lock claim
        claim_conn = get_db(worker_env=env)
        claimed = acquire_atomic_run_lock(claim_conn, user_id, now_utc=now_utc)
        if hasattr(claim_conn, "close"):
            claim_conn.close()

        if not claimed:
            skipped.append({"user_id": user_id, "reason": "lock_claim_failed_or_concurrent"})
            continue

        # Execute daily run with guaranteed lock release in finally block
        lock_released = False
        try:
            run_result = await execute_daily_run(user_id, trigger_type="scheduled")
            status = run_result.get("status", "completed")
            next_run = calculate_next_run(u.get("preferred_time", "08:00"), u.get("timezone", "UTC"))

            rel_conn = get_db(worker_env=env)
            release_run_lock(rel_conn, user_id, status=status, next_run_at=next_run)
            lock_released = True
            if hasattr(rel_conn, "close"):
                rel_conn.close()

            triggered.append({"user_id": user_id, "status": status, "run_id": run_result.get("run_id")})
        except Exception as e:
            logger.error(f"Scheduled run failed for user {user_id}: {e}", exc_info=True)
            if not lock_released:
                rel_conn = get_db(worker_env=env)
                release_run_lock(rel_conn, user_id, status="failed")
                lock_released = True
                if hasattr(rel_conn, "close"):
                    rel_conn.close()
            errors.append({"user_id": user_id, "error": str(e)})
        finally:
            if not lock_released:
                try:
                    rel_conn = get_db(worker_env=env)
                    release_run_lock(rel_conn, user_id, status="failed")
                    if hasattr(rel_conn, "close"):
                        rel_conn.close()
                except Exception:
                    pass

    return {
        "success": len(errors) == 0,
        "users_checked": len(users_to_check),
        "runs_triggered": len(triggered),
        "runs_skipped": len(skipped),
        "triggered_details": triggered,
        "errors": errors
    }

class DailyRunScheduler:
    """
    Lightweight, non-blocking asynchronous scheduler for local development.
    Preserves local continuous polling while delegating core execution to run_scheduled_tick.
    """
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def start(self, force: bool = False):
        if self._running:
            return
        import os
        # Avoid running background ticker during automated test suites unless forced
        if not force and (os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TESTING") == "1"):
            return
        self._running = True
        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._loop())
        except RuntimeError:
            self._task = None
        logger.info("DailyRunScheduler local background service started.")

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        logger.info("DailyRunScheduler local background service stopped.")

    async def _loop(self):
        while self._running:
            try:
                await self._check_and_trigger_runs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler tick error: {e}", exc_info=True)

            try:
                # Local tick interval: 30 seconds
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break

    async def _check_and_trigger_runs(self):
        await run_scheduled_tick()

# Global singleton scheduler instance for local development
scheduler = DailyRunScheduler()
