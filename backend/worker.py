"""
Cloudflare Python Worker Entrypoint for Personal AI Assistant.
Provides:
1. Lazy ASGI HTTP bridge (via workers.asgi.entrypoint) for FastAPI application.
   Ensures zero entropy/randomness calls during top-level snapshot creation.
2. Cloudflare Cron Triggers handler (via WorkerEntrypoint scheduled) for Daily Briefing & Scheduled Runs.
3. Injection of Cloudflare environment bindings (D1 Database, Secrets, KV, AI).
"""
import asyncio
import logging
import os
import sys
from typing import Any, Optional

# Ensure vendored Pyodide python_modules directory is on sys.path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
modules_dir = os.path.join(parent_dir, "python_modules")
if os.path.exists(modules_dir) and modules_dir not in sys.path:
    sys.path.insert(0, modules_dir)

logger = logging.getLogger("worker")

_app = None
_asgi_handler = None

def get_app():
    """Lazily loads FastAPI application inside request handler to avoid top-level entropy violations."""
    global _app
    if _app is None:
        from .main import app
        _app = app
    return _app

def get_asgi_handler():
    """Lazily creates and caches the native workers.asgi handler."""
    global _asgi_handler
    if _asgi_handler is None:
        from workers import asgi
        app = get_app()
        _asgi_handler = asgi.entrypoint(app)
    return _asgi_handler

async def handle_worker_scheduled_tick(env: Optional[Any] = None) -> dict:
    """
    Executes a scheduled run check under the provided Cloudflare Worker environment.
    Designed to be invoked by Cloudflare Cron Triggers (e.g., every 15 minutes).
    """
    from .main import current_worker_env
    token = current_worker_env.set(env)
    try:
        from .scheduler import run_scheduled_tick
        return await run_scheduled_tick(env=env)
    except Exception as e:
        logger.error(f"Worker scheduled tick execution failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
    finally:
        current_worker_env.reset(token)

# Detect if running in Cloudflare Python Worker runtime
try:
    from workers import WorkerEntrypoint
    HAS_WORKERS_RUNTIME = True
except ImportError:
    HAS_WORKERS_RUNTIME = False

if HAS_WORKERS_RUNTIME:
    class Default(WorkerEntrypoint):
        async def fetch(self, request):
            """Handles incoming HTTP traffic via lazily-loaded FastAPI ASGI."""
            handler = get_asgi_handler()
            return await handler(request, self.env, self.ctx)

        async def scheduled(self, *args, **kwargs):
            """Handles Cloudflare Cron Triggers."""
            env = getattr(self, "env", None)
            if not env and len(args) > 1:
                env = args[1]
            return await handle_worker_scheduled_tick(env)
else:
    class LocalASGIProxy:
        async def __call__(self, scope, receive, send):
            app = get_app()
            return await app(scope, receive, send)

    Default = LocalASGIProxy()

default = Default
__all__ = ["Default", "default", "get_app", "get_asgi_handler", "handle_worker_scheduled_tick"]
