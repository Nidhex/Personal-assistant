import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import FastAPI, Request, Response, HTTPException, Depends, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from .database import init_db, get_db
from .security import (
    generate_session_id,
    generate_oauth_state,
    get_session_expiry,
    is_expired,
    encrypt_token
)
from .google_service import (
    is_google_configured,
    get_google_auth_url,
    exchange_code_for_tokens,
    get_google_user_profile,
    fetch_gmail_messages,
    fetch_gmail_message_detail,
    revoke_user_tokens,
    FRONTEND_URL,
    GOOGLE_SCOPES
)

load_dotenv()

# Initialize DB on startup
init_db()

app = FastAPI(title="Personal Assistant API", version="1.0.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEV_TEST_MODE = os.getenv("DEV_TEST_MODE", "false").lower() == "true"

# -------------------------------------------------------------
# AUTHENTICATION DEPENDENCY
# -------------------------------------------------------------
def get_current_user_optional(request: Request) -> Optional[dict]:
    session_id = request.cookies.get("session_id")
    if not session_id:
        # Fallback to Authorization header if provided
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            session_id = auth_header.split(" ")[1]

    if not session_id:
        return None

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.session_id, s.expires_at, u.id, u.email, u.name, u.picture
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.session_id = ?
    """, (session_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return None

    if is_expired(row["expires_at"]):
        cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()
        return None

    # Check gmail connection status
    cursor.execute("""
        SELECT gmail_connected, scopes FROM user_tokens WHERE user_id = ?
    """, (row["id"],))
    token_row = cursor.fetchone()
    gmail_connected = bool(token_row["gmail_connected"]) if token_row else False
    scopes = token_row["scopes"].split(" ") if token_row and token_row["scopes"] else []

    conn.close()

    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "picture": row["picture"],
        "gmail_connected": gmail_connected,
        "scopes": scopes
    }

def get_current_user(request: Request) -> dict:
    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in."
        )
    return user

# -------------------------------------------------------------
# AUTH & OAUTH ROUTES
# -------------------------------------------------------------
@app.get("/api/auth/status")
def auth_status():
    """Returns Google OAuth configuration readiness and dev mode flag."""
    configured = is_google_configured()
    return {
        "google_configured": configured,
        "dev_test_mode_enabled": DEV_TEST_MODE,
        "missing_keys": [
            k for k, v in [
                ("GOOGLE_CLIENT_ID", os.getenv("GOOGLE_CLIENT_ID")),
                ("GOOGLE_CLIENT_SECRET", os.getenv("GOOGLE_CLIENT_SECRET"))
            ] if not v
        ],
        "scopes_requested": GOOGLE_SCOPES
    }

@app.get("/api/auth/me")
def get_me(request: Request):
    """Returns current active authenticated user or unauthenticated status."""
    user = get_current_user_optional(request)
    if not user:
        return {"authenticated": False, "user": None, "gmail_connected": False}
    return {
        "authenticated": True,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "picture": user["picture"]
        },
        "gmail_connected": user["gmail_connected"],
        "scopes": user["scopes"]
    }

@app.get("/api/auth/google/url")
def get_auth_url(user: Optional[dict] = Depends(get_current_user_optional)):
    """Generates secure state and returns official Google OAuth URL."""
    if not is_google_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth credentials not configured on the server. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env."
        )

    state = generate_oauth_state()
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()

    conn = get_db()
    conn.execute("""
        INSERT INTO oauth_states (state, action, user_id, expires_at)
        VALUES (?, ?, ?, ?)
    """, (state, "login", user["id"] if user else None, expires_at))
    conn.commit()
    conn.close()

    url = get_google_auth_url(state)
    return {"auth_url": url}

@app.get("/api/auth/google/callback")
async def google_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None
):
    """Handles Google redirect, exchanges code, verifies state, sets session cookie."""
    if error:
        return RedirectResponse(f"{FRONTEND_URL}/?auth_error={error}")

    if not code or not state:
        return RedirectResponse(f"{FRONTEND_URL}/?auth_error=missing_parameters")

    # Validate state CSRF
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT state, action, user_id, expires_at FROM oauth_states WHERE state = ?", (state,))
    row = cursor.fetchone()

    if not row or is_expired(row["expires_at"]):
        conn.close()
        return RedirectResponse(f"{FRONTEND_URL}/?auth_error=invalid_or_expired_state")

    # Remove used state
    cursor.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
    conn.commit()

    try:
        # Exchange code for tokens
        token_data = await exchange_code_for_tokens(code)
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        token_expiry = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
        granted_scopes = token_data.get("scope", "")

        # Fetch Google profile
        profile = await get_google_user_profile(access_token)
        google_id = str(profile.get("id"))
        email = profile.get("email")
        name = profile.get("name", email.split("@")[0] if email else "User")
        picture = profile.get("picture", "")

        user_id = f"usr_{google_id}"

        # Upsert user
        cursor.execute("""
            INSERT INTO users (id, email, name, picture, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                email = excluded.email,
                name = excluded.name,
                picture = excluded.picture
        """, (user_id, email, name, picture, datetime.now(timezone.utc).isoformat()))

        # Check if we already have a refresh token stored if Google didn't return one this time
        if not refresh_token:
            cursor.execute("SELECT refresh_token_encrypted FROM user_tokens WHERE user_id = ?", (user_id,))
            existing = cursor.fetchone()
            if existing and existing["refresh_token_encrypted"]:
                # Keep existing encrypted refresh token
                encrypted_refresh = existing["refresh_token_encrypted"]
            else:
                encrypted_refresh = ""
        else:
            encrypted_refresh = encrypt_token(refresh_token)

        # Upsert user tokens
        cursor.execute("""
            INSERT INTO user_tokens (
                user_id, access_token_encrypted, refresh_token_encrypted, 
                token_expiry, scopes, gmail_connected, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                access_token_encrypted = excluded.access_token_encrypted,
                refresh_token_encrypted = CASE WHEN excluded.refresh_token_encrypted != '' THEN excluded.refresh_token_encrypted ELSE user_tokens.refresh_token_encrypted END,
                token_expiry = excluded.token_expiry,
                scopes = excluded.scopes,
                gmail_connected = 1,
                updated_at = excluded.updated_at
        """, (
            user_id,
            encrypt_token(access_token),
            encrypted_refresh,
            token_expiry,
            granted_scopes,
            datetime.now(timezone.utc).isoformat()
        ))

        # Create session
        session_id = generate_session_id()
        expires_at = get_session_expiry(days=7)
        cursor.execute("""
            INSERT INTO sessions (session_id, user_id, expires_at, created_at)
            VALUES (?, ?, ?, ?)
        """, (session_id, user_id, expires_at, datetime.now(timezone.utc).isoformat()))

        conn.commit()
        conn.close()

        # Set HTTP-only session cookie and redirect
        response = RedirectResponse(f"{FRONTEND_URL}/?auth_success=1")
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            samesite="lax",
            secure=False,  # localhost friendly
            max_age=7 * 24 * 3600
        )
        return response

    except Exception as e:
        conn.close()
        return RedirectResponse(f"{FRONTEND_URL}/?auth_error={str(e)}")

@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    """Destroys current session and deletes session cookie."""
    session_id = request.cookies.get("session_id")
    if session_id:
        conn = get_db()
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()

    response = JSONResponse({"success": True, "message": "Signed out successfully."})
    response.delete_cookie(key="session_id")
    return response

# -------------------------------------------------------------
# DEV TEST MODE AUTH (EXPLICITLY GATED)
# -------------------------------------------------------------
class DevLoginRequest(BaseModel):
    user_id: Optional[str] = "usr_dev_test"
    email: Optional[str] = "developer@test.local"
    name: Optional[str] = "Test Developer"

@app.post("/api/auth/dev-login")
def dev_login(req: DevLoginRequest, response: Response):
    """Only enabled when DEV_TEST_MODE=true in .env for local offline testing."""
    if not DEV_TEST_MODE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Development test login is disabled. Configure Google OAuth in .env to sign in."
        )

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (id, email, name, picture, created_at)
        VALUES (?, ?, ?, '', ?)
        ON CONFLICT(id) DO UPDATE SET email = excluded.email, name = excluded.name
    """, (req.user_id, req.email, req.name, datetime.now(timezone.utc).isoformat()))

    session_id = generate_session_id()
    cursor.execute("""
        INSERT INTO sessions (session_id, user_id, expires_at, created_at)
        VALUES (?, ?, ?, ?)
    """, (session_id, req.user_id, get_session_expiry(7), datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()

    res = JSONResponse({"success": True, "user_id": req.user_id, "email": req.email})
    res.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=7 * 24 * 3600
    )
    return res

# -------------------------------------------------------------
# GMAIL INBOX API (READ-ONLY, USER ISOLATED)
# -------------------------------------------------------------
@app.get("/api/gmail/messages")
async def get_messages(
    max_results: int = Query(15, ge=1, le=30),
    page_token: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Retrieves real messages from the authenticated user's Gmail inbox."""
    if not user.get("gmail_connected"):
        return {
            "connected": False,
            "messages": [],
            "nextPageToken": None,
            "message": "Connect your Gmail account to view your inbox."
        }

    try:
        data = await fetch_gmail_messages(
            user_id=user["id"],
            max_results=max_results,
            page_token=page_token
        )
        return {
            "connected": True,
            "messages": data["messages"],
            "nextPageToken": data["nextPageToken"],
            "resultSizeEstimate": data["resultSizeEstimate"]
        }
    except Exception as e:
        # Check if authorization expired or revoked
        err_msg = str(e)
        if "unauthorized" in err_msg.lower() or "revoked" in err_msg.lower() or "expired" in err_msg.lower():
            return {
                "connected": False,
                "messages": [],
                "nextPageToken": None,
                "error": "Gmail authorization has expired or was revoked. Please reconnect."
            }
        raise HTTPException(status_code=500, detail=f"Failed to fetch Gmail messages: {err_msg}")

@app.get("/api/gmail/messages/{message_id}")
async def get_message_detail(
    message_id: str,
    user: dict = Depends(get_current_user)
):
    """Retrieves sanitized details of a specific message belonging to the user."""
    if not user.get("gmail_connected"):
        raise HTTPException(status_code=400, detail="Gmail is not connected.")

    try:
        detail = await fetch_gmail_message_detail(user["id"], message_id)
        return detail
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/gmail/disconnect")
async def disconnect_gmail(user: dict = Depends(get_current_user)):
    """Revokes token and disconnects Gmail for current user."""
    try:
        await revoke_user_tokens(user["id"])
        return {"success": True, "gmail_connected": False, "message": "Gmail disconnected successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------
# USER DATA ENDPOINTS (STRICT USER ISOLATION)
# -------------------------------------------------------------
@app.get("/api/user/data")
def get_user_data(user: dict = Depends(get_current_user)):
    """Returns all private data items for the authenticated user."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, source, source_email_id, due_date, priority, completed, workspace
        FROM user_tasks WHERE user_id = ? ORDER BY created_at DESC
    """, (user["id"],))
    tasks = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT id, name, type, description
        FROM user_workspaces WHERE user_id = ? ORDER BY created_at DESC
    """, (user["id"],))
    workspaces = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT id, type, target, subject, reason, risk_level, draft_content, status, created_at
        FROM user_approvals WHERE user_id = ? AND status = 'pending' ORDER BY created_at DESC
    """, (user["id"],))
    approvals = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT id, trigger, status, latency, result, created_at
        FROM user_activity WHERE user_id = ? ORDER BY created_at DESC LIMIT 20
    """, (user["id"],))
    activity = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return {
        "tasks": tasks,
        "workspaces": workspaces,
        "approvals": approvals,
        "activity": activity
    }

class CreateTaskRequest(BaseModel):
    title: str
    source: Optional[str] = "User Created"
    source_email_id: Optional[str] = None
    due_date: Optional[str] = "No due date"
    priority: Optional[str] = "normal"
    workspace: Optional[str] = "General"

@app.post("/api/user/tasks")
def create_task(req: CreateTaskRequest, user: dict = Depends(get_current_user)):
    task_id = f"tsk_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{os.urandom(2).hex()}"
    conn = get_db()
    conn.execute("""
        INSERT INTO user_tasks (id, user_id, title, source, source_email_id, due_date, priority, completed, workspace, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
    """, (task_id, user["id"], req.title, req.source, req.source_email_id, req.due_date, req.priority, req.workspace, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()
    return {"success": True, "id": task_id, "title": req.title}

@app.post("/api/user/tasks/{task_id}/toggle")
def toggle_task(task_id: str, user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT completed FROM user_tasks WHERE id = ? AND user_id = ?", (task_id, user["id"]))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Task not found.")

    new_val = 0 if row["completed"] else 1
    cursor.execute("UPDATE user_tasks SET completed = ? WHERE id = ? AND user_id = ?", (new_val, task_id, user["id"]))
    conn.commit()
    conn.close()
    return {"success": True, "completed": bool(new_val)}

class CreateWorkspaceRequest(BaseModel):
    name: str
    type: str = "General"
    description: Optional[str] = ""

@app.post("/api/user/workspaces")
def create_workspace(req: CreateWorkspaceRequest, user: dict = Depends(get_current_user)):
    ws_id = f"ws_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{os.urandom(2).hex()}"
    conn = get_db()
    conn.execute("""
        INSERT INTO user_workspaces (id, user_id, name, type, description, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (ws_id, user["id"], req.name, req.type, req.description, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()
    return {"success": True, "id": ws_id, "name": req.name}

class ApprovalActionRequest(BaseModel):
    action: str  # 'approve' or 'reject'

@app.post("/api/user/approvals/{approval_id}/action")
def handle_approval_action(approval_id: str, req: ApprovalActionRequest, user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM user_approvals WHERE id = ? AND user_id = ?", (approval_id, user["id"]))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Approval item not found.")

    new_status = "approved" if req.action == "approve" else "rejected"
    cursor.execute("UPDATE user_approvals SET status = ? WHERE id = ? AND user_id = ?", (new_status, approval_id, user["id"]))
    conn.commit()
    conn.close()
    return {"success": True, "status": new_status}
