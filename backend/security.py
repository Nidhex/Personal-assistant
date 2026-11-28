import os
import secrets
import threading
from typing import Optional
from datetime import datetime, timedelta, timezone
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

DEV_FALLBACK_KEY = "amUwv28ARP6pPIJSXavvJB02gs678FhhYcPt_BINE5k="

def _validate_fernet_key(key: str) -> bool:
    """Validates that a key is a valid 32-byte base64-encoded Fernet key."""
    if not key or not isinstance(key, str):
        return False
    try:
        Fernet(key.strip().encode("utf-8"))
        return True
    except Exception:
        return False

def is_worker_context(worker_env=None) -> bool:
    """
    Detects whether the application is running within a Cloudflare Worker runtime context.
    Checks:
    1. Explicit worker_env parameter passed to function
    2. Active ContextVar current_worker_env (set by ASGI middleware)
    3. Process environment flags WORKER_ENV=1 or CF_PAGES=1
    """
    if worker_env is not None:
        return True

    try:
        from .main import current_worker_env
        if current_worker_env.get() is not None:
            return True
    except Exception:
        pass

    if os.getenv("WORKER_ENV") == "1" or os.getenv("CF_PAGES") == "1":
        return True

    return False

def is_production(worker_env=None) -> bool:
    """
    Determines whether the application is running in production.
    Checks explicit worker_env binding, active ContextVar, and process environment variables.
    """
    if worker_env is not None:
        val = getattr(worker_env, "ENVIRONMENT", None) if hasattr(worker_env, "ENVIRONMENT") else (worker_env.get("ENVIRONMENT") if isinstance(worker_env, dict) else None)
        if val and str(val).strip().lower() == "production":
            return True

    try:
        from .main import current_worker_env
        env = current_worker_env.get()
        if env is not None:
            val = getattr(env, "ENVIRONMENT", None) if hasattr(env, "ENVIRONMENT") else (env.get("ENVIRONMENT") if isinstance(env, dict) else None)
            if val and str(val).strip().lower() == "production":
                return True
    except Exception:
        pass

    if os.getenv("ENVIRONMENT", "").strip().lower() == "production":
        return True

    return False

def get_encryption_key(worker_env=None) -> str:
    """
    Resolves encryption key from:
    1. Active Cloudflare Worker environment binding (request context or explicit)
    2. Process environment variable (local .env)
    3. Stable development fallback key (strictly non-worker, non-production only)

    In Cloudflare Worker context or production (ENVIRONMENT=production), missing or invalid ENCRYPTION_KEY
    raises RuntimeError immediately to prevent encrypting data with a dev fallback key.
    """
    key: Optional[str] = None

    if worker_env is not None:
        if hasattr(worker_env, "ENCRYPTION_KEY") and getattr(worker_env, "ENCRYPTION_KEY"):
            key = str(getattr(worker_env, "ENCRYPTION_KEY")).strip()
        elif isinstance(worker_env, dict) and worker_env.get("ENCRYPTION_KEY"):
            key = str(worker_env.get("ENCRYPTION_KEY")).strip()

    if not key:
        try:
            from .main import current_worker_env
            env = current_worker_env.get()
            if env is not None:
                if hasattr(env, "ENCRYPTION_KEY") and getattr(env, "ENCRYPTION_KEY"):
                    key = str(getattr(env, "ENCRYPTION_KEY")).strip()
                elif isinstance(env, dict) and env.get("ENCRYPTION_KEY"):
                    key = str(env.get("ENCRYPTION_KEY")).strip()
        except Exception:
            pass

    if not key:
        env_key = os.getenv("ENCRYPTION_KEY")
        if env_key and env_key.strip():
            key = env_key.strip()

    is_worker = is_worker_context(worker_env)
    in_prod = is_production(worker_env)

    if is_worker or in_prod:
        if not key:
            raise RuntimeError(
                "ENCRYPTION_KEY is required in Cloudflare Worker or production environment but was not found."
            )
        if not _validate_fernet_key(key):
            raise RuntimeError(
                "Invalid ENCRYPTION_KEY configured for Cloudflare Worker or production environment. Key must be a valid 32-byte base64-encoded Fernet key."
            )
        return key

    if key:
        return key

    return DEV_FALLBACK_KEY

# Thread-safe, context-safe Fernet instance cache mapped by key value
_fernet_cache: dict[str, Fernet] = {}
_cache_lock = threading.Lock()

def get_fernet_for_key(key_str: str) -> Fernet:
    """Returns or creates a Fernet cipher instance for a given valid Fernet key in a thread-safe manner."""
    instance = _fernet_cache.get(key_str)
    if instance is not None:
        return instance
    with _cache_lock:
        if key_str not in _fernet_cache:
            k_bytes = key_str.encode("utf-8") if isinstance(key_str, str) else key_str
            _fernet_cache[key_str] = Fernet(k_bytes)
        return _fernet_cache[key_str]

def get_fernet(worker_env=None) -> Fernet:
    """Resolves the authoritative encryption key for the current context and returns its Fernet instance."""
    key_str = get_encryption_key(worker_env=worker_env)
    return get_fernet_for_key(key_str)

# Lazy accessor for backwards compatibility with existing imports
class _LazyFernet:
    def __getattr__(self, name):
        return getattr(get_fernet(), name)

fernet = _LazyFernet()

def encrypt_token(token: str, worker_env=None) -> str:
    if not token:
        return ""
    return get_fernet(worker_env=worker_env).encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str, worker_env=None) -> str:
    if not encrypted_token:
        return ""
    fernet_inst = get_fernet(worker_env=worker_env)
    try:
        return fernet_inst.decrypt(encrypted_token.encode()).decode()
    except Exception:
        return ""

def generate_session_id() -> str:
    return secrets.token_urlsafe(32)

def generate_oauth_state() -> str:
    return secrets.token_urlsafe(24)

def get_session_expiry(days: int = 7) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

def is_expired(iso_timestamp: str) -> bool:
    if not iso_timestamp:
        return True
    try:
        ts = str(iso_timestamp).strip()
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > dt
    except Exception:
        return True
