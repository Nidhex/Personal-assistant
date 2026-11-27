import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional

from .database import get_db
from .orchestrator import execute_daily_run, calculate_next_run

logger = logging.getLogger("scheduler")

class DailyRunScheduler:
    """
    Lightweight, non-blocking asynchronous scheduler that manages daily agent runs.
    - Honors user-configured timezones and execution hours.
    - Opt-in: only triggers for users with daily_run_enabled = 1.
    - Strictly prevents duplicate runs on the same calendar day.
    - Recovers state from SQLite database on backend startup.
    """
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_triggered_date = {} # maps user_id -> date_str of last scheduled trigger

    def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("DailyRunScheduler background service started.")

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("DailyRunScheduler background service stopped.")

    async def _loop(self):
        while self._running:
            try:
                await self._check_and_trigger_runs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler tick error: {e}", exc_info=True)
            
            # Tick every 30 seconds to catch preferred minute accurately without drifting
            await asyncio.sleep(30)

    async def _check_and_trigger_runs(self):
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, preferred_time, timezone, daily_run_enabled, last_run_at
            FROM user_agent_settings
            WHERE daily_run_enabled = 1
        """)
        users_to_check = [dict(r) for r in cursor.fetchall()]
        conn.close()

        for u in users_to_check:
            user_id = u["user_id"]
            tz_str = u.get("timezone", "UTC")
            pref_time = u.get("preferred_time", "08:00")
            last_run_at = u.get("last_run_at")

            try:
                user_tz = ZoneInfo(tz_str)
            except Exception:
                user_tz = ZoneInfo("UTC")

            now_user = datetime.now(user_tz)
            today_str = now_user.strftime("%Y-%m-%d")
            current_hm = now_user.strftime("%H:%M")

            # Check if preferred minute has arrived
            if current_hm == pref_time:
                # Deduplication check 1: memory cache for today
                if self._last_triggered_date.get(user_id) == today_str:
                    continue

                # Deduplication check 2: database last_run_at check
                if last_run_at:
                    try:
                        last_dt = datetime.fromisoformat(last_run_at).astimezone(user_tz)
                        if last_dt.strftime("%Y-%m-%d") == today_str:
                            continue
                    except Exception:
                        pass

                # Mark triggered for today to prevent double-firing
                self._last_triggered_date[user_id] = today_str
                logger.info(f"Triggering scheduled daily run for user {user_id} at {current_hm} ({tz_str}).")
                
                # Execute unattended run in background
                asyncio.create_task(execute_daily_run(user_id, trigger_type="scheduled"))

# Global singleton scheduler instance
scheduler = DailyRunScheduler()
