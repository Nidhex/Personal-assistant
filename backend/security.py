import os
import secrets
from datetime import datetime, timedelta, timezone
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

# Key for encrypting OAuth tokens at rest
_ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not _ENCRYPTION_KEY:
    # Stable fallback key for dev environment if not set
    _ENCRYPTION_KEY = "amUwv28ARP6pPIJSXavvJB02gs678FhhYcPt_BINE5k="

fernet = Fernet(_ENCRYPTION_KEY.encode() if isinstance(_ENCRYPTION_KEY, str) else _ENCRYPTION_KEY)

def encrypt_token(token: str) -> str:
    if not token:
        return ""
    return fernet.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    if not encrypted_token:
        return ""
    try:
        return fernet.decrypt(encrypted_token.encode()).decode()
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
        return datetime.now(timezone.utc) > dt
    except Exception:
        return True
