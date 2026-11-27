# Cloudflare Python Worker Backend Configuration Guide

This guide details the Cloudflare Python Worker deployment architecture, environment bindings, secrets, and integration with Cloudflare D1.

---

## 1. Runtime Architecture

- **Runtime**: Cloudflare Workers with Python (`python_workers` compatibility flag).
- **Engine**: Pyodide (CPython compiled to WebAssembly) running inside V8 isolates.
- **Entrypoint**: `worker.py` -> `backend.worker:default` (`workers.asgi.entrypoint(app)`).
- **Database**: Cloudflare D1 database accessed via the `DB` binding.
- **Scheduling**: Cloudflare Cron Triggers (`scheduled()` handler) running every 15 minutes.

---

## 2. Environment Bindings

Configured in `wrangler.jsonc`:

| Binding Name | Type | Description |
| :--- | :--- | :--- |
| `DB` | `d1_database` | Cloudflare D1 database binding (`deskagent-db`). |
| `crons` | `triggers` | Periodic trigger `*/15 * * * *` executing `handle_worker_scheduled_tick`. |

---

## 3. Required Secrets (Stored via `wrangler secret put`)

These values must NOT be committed to version control and should be set using `npx wrangler secret put <NAME>`:

| Secret Name | Purpose | Example / Format |
| :--- | :--- | :--- |
| `ENCRYPTION_KEY` | Fernet key for encrypting OAuth tokens at rest | 32-byte urlsafe base64 string (generate via `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) |
| `GOOGLE_CLIENT_ID` | Google OAuth 2.0 Web Client ID | `<id>.apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | Google OAuth 2.0 Client Secret | `<secret>` |
| `GEMINI_API_KEY` | Google Gemini AI API key for conversational agent | `AIzaSy...` |

---

## 4. Public Environment Variables (`vars` in `wrangler.jsonc`)

| Variable | Recommended Production Value | Description |
| :--- | :--- | :--- |
| `ENVIRONMENT` | `production` | Enforces production security checks (disables dev login). |
| `COOKIE_SECURE` | `true` | Ensures auth session cookies only transmit over HTTPS. |
| `DEV_TEST_MODE` | `false` | Disables mock authentication bypasses. |
| `FRONTEND_URL` | `https://deskagent.pages.dev` | Production Cloudflare Pages URL for OAuth redirects. |
| `GOOGLE_REDIRECT_URI` | `https://deskagent-backend.<subdomain>.workers.dev/api/auth/google/callback` | OAuth redirect callback URI registered in Google Cloud Console. |

---

## 5. Local Development vs. Worker Execution

| Aspect | Local Development | Cloudflare Worker (Production) |
| :--- | :--- | :--- |
| **Server** | `uvicorn backend.main:app` | Native Cloudflare ASGI (`workers.asgi`) |
| **Database** | SQLite (`backend/data.db`) | Cloudflare D1 (`env.DB`) |
| **Background Tasks** | Asyncio infinite loop in `scheduler.py` | Cloudflare Cron Triggers (`scheduled()`) |
| **Configuration** | Local `.env` file | Worker `env` bindings & Cloudflare Secrets |
