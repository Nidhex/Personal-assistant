import os
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

# Exact permissions requested for initial MVP (strictly read-only)
GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly"
]

def is_google_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

def get_google_auth_url(state: str) -> str:
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

async def exchange_code_for_tokens(code: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": GOOGLE_REDIRECT_URI
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
    cursor.execute("""
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
        conn.execute("UPDATE user_tokens SET gmail_connected = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        raise Exception("Google authorization expired and no refresh token is present. Please reconnect.")

    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "refresh_type": "refresh_token",
                "refresh_token": refresh_token,
                "grant_type": "refresh_token"
            },
            timeout=15.0
        )

        if res.status_code != 200:
            # Refresh token was revoked by user or expired
            conn = get_db()
            conn.execute("UPDATE user_tokens SET gmail_connected = 0 WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            raise Exception(f"Google token refresh failed: {res.text}. Access was likely revoked.")

        data = res.json()
        new_access_token = data.get("access_token")
        expires_in = data.get("expires_in", 3600)
        new_expiry = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

        conn = get_db()
        conn.execute("""
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
    cursor.execute("""
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

        cursor.execute("""
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
            # Base64 URL safe decoding
            decoded_bytes = base64.urlsafe_b64decode(data + "==")
            return decoded_bytes.decode("utf-8", errors="replace")
        except Exception:
            return ""
    return ""

def _extract_message_body(payload) -> str:
    """Traverses multipart MIME tree to extract clean message text."""
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if body_data:
        try:
            decoded_bytes = base64.urlsafe_b64decode(body_data + "==")
            text = decoded_bytes.decode("utf-8", errors="replace")
            # If html, strip tags simply for safe display
            if "html" in mime_type:
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()
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
        return plain_text.strip()
    if html_text.strip():
        # Strip html tags
        clean = re.sub(r'<[^>]+>', ' ', html_text)
        return re.sub(r'\s+', ' ', clean).strip()

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

        # Fetch metadata for each message
        messages = []
        for item in message_summaries:
            msg_id = item["id"]
            msg_res = await client.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
                timeout=10.0
            )
            if msg_res.status_code != 200:
                continue

            msg_data = msg_res.json()
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

        return {
            "id": message_id,
            "threadId": msg_data.get("threadId"),
            "senderName": sender_name or sender_email,
            "senderEmail": sender_email,
            "subject": headers.get("subject", "(No Subject)"),
            "date": headers.get("date", ""),
            "snippet": msg_data.get("snippet", ""),
            "body": body or msg_data.get("snippet", "(No message body content)"),
            "isUnread": "UNREAD" in msg_data.get("labelIds", []),
            "labels": msg_data.get("labelIds", [])
        }
