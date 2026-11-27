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
    class Default(WorkerEntrypoint):
        async def fetch(self, request):
            from backend.worker import get_asgi_handler
            handler = get_asgi_handler()
            return await handler(request, self.env, self.ctx)

        async def scheduled(self, controller):
            from backend.worker import handle_worker_scheduled_tick
            return await handle_worker_scheduled_tick(self.env)
else:
    from backend.worker import default
    Default = default

default = Default
__all__ = ["Default", "default"]
