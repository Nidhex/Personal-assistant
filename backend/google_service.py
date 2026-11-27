import os
import asyncio
import base64
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
import httpx
from dotenv import load_dotenv

from .security import encrypt_token, decrypt_token, is_expired
from .database import get_db

load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8001/api/auth/google/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

def get_config_val(name: str, default: str = "") -> str:
    """Resolves configuration value from current Cloudflare Worker env or process env."""
    try:
        from .main import current_worker_env
        env = current_worker_env.get()
        if env and hasattr(env, name) and getattr(env, name):
            return str(getattr(env, name))
    except Exception:
        pass
    return os.getenv(name, default)

def is_production(request=None) -> bool:
    """
    Determines whether the application is running in production.
    Checks Worker bindings, process env, Worker runtime flags, and request headers.
    """
    env_str = get_config_val("ENVIRONMENT", "").lower()
    if env_str == "production":
        return True
    if os.getenv("ENVIRONMENT", "").lower() == "production":
        return True
    if os.getenv("WORKER_ENV") == "1" or os.getenv("CF_PAGES") == "1":
        return True
    try:
        from .main import current_worker_env
        w_env = current_worker_env.get()
        if w_env is not None:
            w_val = getattr(w_env, "ENVIRONMENT", None)
            if w_val and str(w_val).lower() == "production":
                return True
            return True
    except Exception:
        pass
    if request:
        req_env = request.scope.get("env") if hasattr(request, "scope") else None
        if req_env:
            w_val = getattr(req_env, "ENVIRONMENT", None)
            if w_val and str(w_val).lower() == "production":
                return True
        host = request.headers.get("host", "").lower() if hasattr(request, "headers") else ""
        if "workers.dev" in host or "pages.dev" in host:
            return True
    return False

def get_frontend_url(request=None) -> str:
    """
    Resolves the canonical frontend URL in an environment-aware manner.
    Guarantees that production requests NEVER redirect to localhost.
    In local development, dynamically resolves LAN IP for mobile dev testing.
    """
    configured_url = get_config_val("FRONTEND_URL", "").strip().rstrip("/")
    is_prod = is_production(request)

    if is_prod:
        is_configured_localhost = "localhost" in configured_url or "127.0.0.1" in configured_url
        if configured_url and not is_configured_localhost:
            return configured_url
        return "https://deskagent.hacckthon.workers.dev"

    # In local development: check if request originates from a LAN IP (e.g. mobile testing on Wi-Fi)
    if request and hasattr(request, "headers"):
        host = request.headers.get("host", "")
        if "workers.dev" in host or "pages.dev" in host:
            return "https://deskagent.hacckthon.workers.dev"
        if ":" in host:
            host_name = host.split(":")[0]
            if host_name not in ["localhost", "127.0.0.1", "testserver"]:
                proto = request.headers.get("x-forwarded-proto", "http")
                return f"{proto}://{host_name}:5173"

    if configured_url:
        return configured_url

    return os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")

def is_cookie_secure(request=None) -> bool:
    if is_production(request):
        return True
    c_sec = get_config_val("COOKIE_SECURE", "")
    if c_sec.lower() == "true":
        return True
    if os.getenv("COOKIE_SECURE", "false").lower() == "true":
        return True
    if request and hasattr(request, "url") and getattr(request.url, "scheme", "") == "https":
        return True
    return False

def is_dev_test_mode(request=None) -> bool:
    if is_production(request):
        return False
    d_val = get_config_val("DEV_TEST_MODE", "")
    if d_val.lower() == "true":
        return True
    return os.getenv("DEV_TEST_MODE", "false").lower() == "true"

# Exact permissions requested for initial MVP (strictly read-only)
GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly"
]

def is_google_configured() -> bool:
    cid = get_config_val("GOOGLE_CLIENT_ID", GOOGLE_CLIENT_ID)
    csecret = get_config_val("GOOGLE_CLIENT_SECRET", GOOGLE_CLIENT_SECRET)
    return bool(cid and csecret)

def get_google_auth_url(state: str, request=None) -> str:
    cid = get_config_val("GOOGLE_CLIENT_ID", GOOGLE_CLIENT_ID)
    redir = get_config_val("GOOGLE_REDIRECT_URI", GOOGLE_REDIRECT_URI)
    if is_production(request) and ("localhost" in redir or "127.0.0.1" in redir or not redir):
        redir = "https://deskagent.hacckthon.workers.dev/api/auth/google/callback"
    params = {
        "client_id": cid,
        "redirect_uri": redir,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

async def exchange_code_for_tokens(code: str, request=None):
    cid = get_config_val("GOOGLE_CLIENT_ID", GOOGLE_CLIENT_ID)
    csecret = get_config_val("GOOGLE_CLIENT_SECRET", GOOGLE_CLIENT_SECRET)
    redir = get_config_val("GOOGLE_REDIRECT_URI", GOOGLE_REDIRECT_URI)
    if is_production(request) and ("localhost" in redir or "127.0.0.1" in redir or not redir):
        redir = "https://deskagent.hacckthon.workers.dev/api/auth/google/callback"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": cid,
                "client_secret": csecret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redir
            },
            timeout=15.0
        )
        if response.status_code != 200:
            raise Exception(f"Google token exchange failed: {response.text}")
        return response.json()

async def get_google_user_profile(access_token: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0
        )
        if response.status_code != 200:
            raise Exception(f"Failed to fetch Google profile: {response.text}")
        return response.json()

async def get_valid_access_token(user_id: str) -> str:
    """Retrieves access token for user, refreshing automatically if expired."""
    conn = get_db()
    cursor = conn.cursor()
    await cursor.execute("""
        SELECT access_token_encrypted, refresh_token_encrypted, token_expiry, gmail_connected
        FROM user_tokens WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row or not row["gmail_connected"]:
        raise Exception("Gmail account is not connected for this user.")

    access_token = decrypt_token(row["access_token_encrypted"])
    refresh_token = decrypt_token(row["refresh_token_encrypted"])
    token_expiry = row["token_expiry"]

    # Check if token is expired or expiring in under 3 minutes
    needs_refresh = False
    if not access_token:
        needs_refresh = True
    elif token_expiry:
        try:
            exp = datetime.fromisoformat(token_expiry)
            if datetime.now(timezone.utc) + timedelta(minutes=3) > exp:
                needs_refresh = True
        except Exception:
            needs_refresh = True

    if not needs_refresh:
        return access_token

    # Token needs refresh
    if not refresh_token:
        # Cannot refresh without refresh_token; mark as disconnected
        conn = get_db()
        await conn.execute("UPDATE user_tokens SET gmail_connected = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        raise Exception("Google authorization expired and no refresh token is present. Please reconnect.")

    cid = get_config_val("GOOGLE_CLIENT_ID", GOOGLE_CLIENT_ID)
    csecret = get_config_val("GOOGLE_CLIENT_SECRET", GOOGLE_CLIENT_SECRET)
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": cid,
                "client_secret": csecret,
                "refresh_type": "refresh_token",
                "refresh_token": refresh_token,
                "grant_type": "refresh_token"
            },
            timeout=15.0
        )

        if res.status_code != 200:
            # Refresh token was revoked by user or expired
            conn = get_db()
            await conn.execute("UPDATE user_tokens SET gmail_connected = 0 WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            raise Exception(f"Google token refresh failed: {res.text}. Access was likely revoked.")

        data = res.json()
        new_access_token = data.get("access_token")
        expires_in = data.get("expires_in", 3600)
        new_expiry = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

        conn = get_db()
        await conn.execute("""
            UPDATE user_tokens 
            SET access_token_encrypted = ?, token_expiry = ?, updated_at = ?
            WHERE user_id = ?
        """, (encrypt_token(new_access_token), new_expiry, datetime.now(timezone.utc).isoformat(), user_id))
        conn.commit()
        conn.close()

        return new_access_token

async def revoke_user_tokens(user_id: str):
    """Revokes access with Google and removes local credentials."""
    conn = get_db()
    cursor = conn.cursor()
    await cursor.execute("""
        SELECT access_token_encrypted, refresh_token_encrypted
        FROM user_tokens WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()

    if row:
        token_to_revoke = decrypt_token(row["refresh_token_encrypted"]) or decrypt_token(row["access_token_encrypted"])
        if token_to_revoke:
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"https://oauth2.googleapis.com/revoke?token={token_to_revoke}",
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                        timeout=5.0
                    )
            except Exception:
                pass  # Revoke silently if already invalid

        await cursor.execute("""
            UPDATE user_tokens 
            SET access_token_encrypted = '', refresh_token_encrypted = '', gmail_connected = 0, updated_at = ?
            WHERE user_id = ?
        """, (datetime.now(timezone.utc).isoformat(), user_id))
        conn.commit()
    conn.close()

def _decode_body_part(part) -> str:
    data = part.get("body", {}).get("data", "")
    if data:
        try:
            # Base64 URL safe decoding with correct padding
            rem = len(data) % 4
            if rem > 0:
                data += "=" * (4 - rem)
            decoded_bytes = base64.urlsafe_b64decode(data)
            return decoded_bytes.decode("utf-8", errors="replace")
        except Exception:
            return ""
    return ""

def _extract_attachments(payload) -> list:
    """Recursively extracts attachment metadata without downloading payload files."""
    attachments = []
    parts = payload.get("parts", [])
    for part in parts:
        filename = part.get("filename", "")
        if filename:
            body = part.get("body", {})
            attachments.append({
                "filename": filename,
                "mimeType": part.get("mimeType", "application/octet-stream"),
                "size": body.get("size", 0),
                "attachmentId": body.get("attachmentId", "")
            })
        if "parts" in part:
            attachments.extend(_extract_attachments(part))
    return attachments

def _extract_message_body(payload) -> str:
    """Traverses multipart MIME tree to extract clean message text, stripping scripts and styling."""
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if body_data:
        try:
            rem = len(body_data) % 4
            if rem > 0:
                body_data += "=" * (4 - rem)
            decoded_bytes = base64.urlsafe_b64decode(body_data)
            text = decoded_bytes.decode("utf-8", errors="replace")
            # If html, strip script, style, and tags simply for safe display
            if "html" in mime_type:
                text = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', text, flags=re.IGNORECASE)
                text = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', text, flags=re.IGNORECASE)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()
                text = re.sub(r'\s+([.,;:!?])', r'\1', text)
            return text
        except Exception:
            pass

    parts = payload.get("parts", [])
    plain_text = ""
    html_text = ""

    for part in parts:
        part_mime = part.get("mimeType", "")
        if part_mime == "text/plain":
            plain_text += _decode_body_part(part)
        elif part_mime == "text/html":
            html_text += _decode_body_part(part)
        elif "multipart" in part_mime:
            sub = _extract_message_body(part)
            if sub:
                plain_text += "\n" + sub

    if plain_text.strip():
        clean = re.sub(r'\s+([.,;:!?])', r'\1', plain_text.strip())
        return clean
    if html_text.strip():
        # Strip script, style, and html tags
        clean = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', html_text, flags=re.IGNORECASE)
        clean = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'<[^>]+>', ' ', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        clean = re.sub(r'\s+([.,;:!?])', r'\1', clean)
        return clean

    return ""

async def fetch_gmail_messages(user_id: str, max_results: int = 15, page_token: str = None):
    """Fetches real Gmail inbox messages using authenticated user token."""
    access_token = await get_valid_access_token(user_id)

    params = {
        "maxResults": min(max_results, 30),
        "q": "in:inbox"
    }
    if page_token:
        params["pageToken"] = page_token

    async with httpx.AsyncClient() as client:
        list_res = await client.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=15.0
        )

        if list_res.status_code == 401 or list_res.status_code == 403:
            # Token revoked or scopes missing
            raise Exception("Gmail access unauthorized. Token may have been revoked.")
        if list_res.status_code != 200:
            raise Exception(f"Failed to fetch messages list from Gmail: {list_res.text}")

        list_data = list_res.json()
        message_summaries = list_data.get("messages", [])
        next_page_token = list_data.get("nextPageToken", None)

        if not message_summaries:
            return {
                "messages": [],
                "nextPageToken": None,
                "resultSizeEstimate": list_data.get("resultSizeEstimate", 0)
            }

        # Fetch metadata for each message concurrently with bounded semaphore to avoid worker subrequest limits
        sem = asyncio.Semaphore(3)
        async def _fetch_single_meta(msg_id: str):
            async with sem:
                try:
                    msg_res = await client.get(
                        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}",
                        headers={"Authorization": f"Bearer {access_token}"},
                        params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
                        timeout=10.0
                    )
                    if msg_res.status_code == 200:
                        return msg_res.json()
                except Exception:
                    pass
                return None

        raw_meta_results = await asyncio.gather(*[_fetch_single_meta(item["id"]) for item in message_summaries])

        messages = []
        for msg_data in raw_meta_results:
            if not msg_data:
                continue

            msg_id = msg_data.get("id")
            headers = {h["name"].lower(): h["value"] for h in msg_data.get("payload", {}).get("headers", [])}
            
            sender_raw = headers.get("from", "Unknown Sender")
            # Parse sender name and email
            sender_name = sender_raw
            sender_email = sender_raw
            if "<" in sender_raw and ">" in sender_raw:
                sender_name = sender_raw.split("<")[0].strip().strip('"')
                sender_email = sender_raw.split("<")[1].split(">")[0].strip()

            label_ids = msg_data.get("labelIds", [])
            is_unread = "UNREAD" in label_ids

            messages.append({
                "id": msg_id,
                "threadId": msg_data.get("threadId"),
                "senderName": sender_name or sender_email,
                "senderEmail": sender_email,
                "from": sender_raw,
                "subject": headers.get("subject", "(No Subject)"),
                "snippet": msg_data.get("snippet", ""),
                "date": headers.get("date", ""),
                "isUnread": is_unread,
                "labels": label_ids
            })

        return {
            "messages": messages,
            "nextPageToken": next_page_token,
            "resultSizeEstimate": list_data.get("resultSizeEstimate", len(messages))
        }

async def fetch_gmail_message_detail(user_id: str, message_id: str):
    """Fetches full sanitized Gmail message content."""
    access_token = await get_valid_access_token(user_id)

    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"format": "full"},
            timeout=15.0
        )

        if res.status_code == 404:
            raise Exception("Email message not found or deleted from Gmail.")
        if res.status_code == 400:
            raise Exception("Invalid Gmail message identifier.")
        if res.status_code != 200:
            raise Exception(f"Failed to fetch message details: {res.text}")

        msg_data = res.json()
        payload = msg_data.get("payload", {})
        headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

        sender_raw = headers.get("from", "Unknown Sender")
        sender_name = sender_raw
        sender_email = sender_raw
        if "<" in sender_raw and ">" in sender_raw:
            sender_name = sender_raw.split("<")[0].strip().strip('"')
            sender_email = sender_raw.split("<")[1].split(">")[0].strip()

        body = _extract_message_body(payload)
        attachments = _extract_attachments(payload)

        return {
            "id": message_id,
            "threadId": msg_data.get("threadId"),
            "senderName": sender_name or sender_email,
            "senderEmail": sender_email,
            "from": sender_raw,
            "recipient": headers.get("to", ""),
            "subject": headers.get("subject", "(No Subject)"),
            "date": headers.get("date", ""),
            "snippet": msg_data.get("snippet", ""),
            "body": body or msg_data.get("snippet", "(No message body content)"),
            "attachments": attachments,
            "isUnread": "UNREAD" in msg_data.get("labelIds", []),
            "labels": msg_data.get("labelIds", [])
        }
