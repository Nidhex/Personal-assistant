"""
Root entrypoint for Cloudflare Workers (referenced by wrangler configuration).
"""
import sys
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
modules_dir = os.path.join(base_dir, "python_modules")
if os.path.exists(modules_dir) and modules_dir not in sys.path:
    sys.path.insert(0, modules_dir)

try:
    from workers import WorkerEntrypoint
    HAS_WORKERS = True
except ImportError:
    HAS_WORKERS = False

if HAS_WORKERS:
    from workers.asgi import fetch as asgi_fetch
    from backend.main import app

    class Default(WorkerEntrypoint):
        async def fetch(self, request):
            return await asgi_fetch(app, request, self.env, self.ctx)

        async def scheduled(self, *args, **kwargs):
            from backend.worker import handle_worker_scheduled_tick
            env = getattr(self, "env", None)
            if not env and len(args) > 1:
                env = args[1]
            return await handle_worker_scheduled_tick(env)
else:
    from backend.worker import default
    Default = default

default = Default
__all__ = ["Default", "default"]
