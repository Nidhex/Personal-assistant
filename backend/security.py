import os
import secrets
from datetime import datetime, timedelta, timezone
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

DEV_FALLBACK_KEY = "amUwv28ARP6pPIJSXavvJB02gs678FhhYcPt_BINE5k="

def get_encryption_key() -> str:
    """
    Resolves encryption key from:
    1. Active Cloudflare Worker environment binding (request context)
    2. Process environment variable (local .env)
    3. Stable development fallback key
    """
    try:
        from .main import current_worker_env
        env = current_worker_env.get()
        if env and hasattr(env, "ENCRYPTION_KEY") and env.ENCRYPTION_KEY:
            return str(env.ENCRYPTION_KEY)
    except Exception:
        pass

    key = os.getenv("ENCRYPTION_KEY")
    if key:
        return key
    return DEV_FALLBACK_KEY

def get_fernet() -> Fernet:
    key_str = get_encryption_key()
    return Fernet(key_str.encode() if isinstance(key_str, str) else key_str)

# Retain module-level fernet for backwards compatibility with existing imports
fernet = get_fernet()

def encrypt_token(token: str) -> str:
    if not token:
        return ""
    return get_fernet().encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    if not encrypted_token:
        return ""
    try:
        return get_fernet().decrypt(encrypted_token.encode()).decode()
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
        dt = datetime.fromisoformat(iso_timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > dt
    except Exception:
        return True
