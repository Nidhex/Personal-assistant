import React, { useState } from 'react'
import {
  ShieldCheck,
  Lock,
  AlertTriangle,
  CheckCircle2,
  KeyRound
} from 'lucide-react'
import { getGoogleAuthUrl, devLogin } from '../api'

export default function LoginView({
  authStatus,
  onAuthSuccess,
  showToast,
  authError,
  onNavigate
}) {
  const [loading, setLoading] = useState(false)
  const [devLoading, setDevLoading] = useState(false)

  const handleGoogleSignIn = async () => {
    setLoading(true)
    try {
      const data = await getGoogleAuthUrl()
      if (data.auth_url) {
        window.location.href = data.auth_url
      }
    } catch (err) {
      setLoading(false)
      showToast(err.message || 'Failed to initiate Google OAuth.')
    }
  }

  const handleDevLogin = async () => {
    setDevLoading(true)
    try {
      await devLogin('dev.user@local.internal', 'Test Engineer')
      showToast('Signed in via development test session.')
      if (onAuthSuccess) onAuthSuccess()
    } catch (err) {
      showToast(err.message || 'Dev sign-in failed.')
    } finally {
      setDevLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#F7F4EB] text-[#242424] flex items-center justify-center p-4 selection:bg-[#B9CDE7] selection:text-[#171717]">
      <div className="w-full max-w-md space-y-6">
        {/* Brand Header */}
        <div className="text-center space-y-2">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-[#FFFDF8] border border-[#DEDAD0] shadow-warm-sm">
            <ShieldCheck className="h-6 w-6 text-[#242424]" />
          </div>
          <h1 className="text-xl font-semibold tracking-tight text-[#242424]">Personal Assistant</h1>
          <p className="text-xs text-[#6B7280]">
            Sign in to access your supervised workspaces, read-only inbox, and schedule.
          </p>
        </div>

        {/* OAuth Error Alert */}
        {authError && (
          <div className="rounded-xl border border-[#EBC1D9] bg-[#FFFDF8] p-4 text-xs text-[#242424] shadow-warm-sm flex items-start gap-3">
            <AlertTriangle className="h-4 w-4 text-[#B91C1C] shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold text-[#B91C1C]">Authentication Error: </span>
              <span>
                {authError === 'access_denied'
                  ? 'Google permissions request was cancelled.'
                  : authError}
              </span>
            </div>
          </div>
        )}

        {/* Main Sign-In Card */}
        <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-7 space-y-5 shadow-warm">
          <div className="space-y-1">
            <h2 className="text-sm font-semibold text-[#242424]">Google Authentication</h2>
            <p className="text-xs text-[#6B7280]">
              Authenticate with your Google account to securely access your read-only Gmail inbox.
            </p>
          </div>

          {/* Google Sign-in Button */}
          <button
            onClick={handleGoogleSignIn}
            disabled={loading || !authStatus.google_configured}
            className="w-full flex items-center justify-center gap-3 rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] px-4 py-3 text-xs font-semibold text-[#242424] hover:bg-[#EFECE2] hover:border-[#242424] transition-all shadow-warm-sm disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24">
              <path
                fill="#4285F4"
                d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.8-2.4 3.65v3.05h3.88c2.27-2.09 3.66-5.17 3.66-9.14z"
              />
              <path
                fill="#34A853"
                d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.15C3.26 21.36 7.33 24 12 24z"
              />
              <path
                fill="#FBBC05"
                d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.25C.45 8.17 0 9.99 0 12s.45 3.83 1.25 5.42l4.03-3.15z"
              />
              <path
                fill="#EA4335"
                d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.33 0 3.26 2.64 1.25 6.58l4.03 3.15c.95-2.83 3.6-4.98 6.72-4.98z"
              />
            </svg>
            <span>{loading ? 'Connecting to Google...' : 'Sign in with Google'}</span>
          </button>

          {/* Requested Scopes & Permissions */}
          <div className="rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-4 text-xs space-y-2.5">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-[#6B7280] block">
              Permissions Requested:
            </span>
            <ul className="space-y-2 text-[11px] text-[#4B5563]">
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-3.5 w-3.5 text-[#242424] shrink-0 mt-0.5" />
                <span>Basic Identity (email, profile info)</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-3.5 w-3.5 text-[#242424] shrink-0 mt-0.5" />
                <span>Gmail read-only inspection (gmail.readonly)</span>
              </li>
              <li className="flex items-start gap-2 text-[#9CA3AF]">
                <Lock className="h-3.5 w-3.5 text-[#9CA3AF] shrink-0 mt-0.5" />
                <span>No send, delete, or compose permission requested</span>
              </li>
            </ul>
          </div>

          {/* Missing Google Credentials Notice */}
          {!authStatus.google_configured && (
            <div className="rounded-xl border border-[#E9DB91] bg-[#FFFDF8] p-4 text-xs text-[#242424] space-y-2 shadow-warm-sm">
              <div className="flex items-center gap-2 font-semibold text-[#854D0E]">
                <KeyRound className="h-4 w-4" />
                <span>Google Cloud Credentials Required</span>
              </div>
              <p className="text-[11px] text-[#713F12] leading-relaxed">
                OAuth 2.0 credentials must be set in your <code className="bg-[#EFECE2] px-1 py-0.5 rounded font-mono text-[#242424]">.env</code> file:
              </p>
              <div className="bg-[#F7F4EB] border border-[#DEDAD0] p-2.5 rounded-lg font-mono text-[10px] text-[#4B5563] space-y-0.5">
                <div>GOOGLE_CLIENT_ID=your_id.apps.googleusercontent.com</div>
                <div>GOOGLE_CLIENT_SECRET=your_secret</div>
                <div>GOOGLE_REDIRECT_URI=http://localhost:8001/api/auth/google/callback</div>
              </div>
            </div>
          )}

          {/* Development Test Login (When Enabled) */}
          {authStatus.dev_test_mode_enabled && (
            <div className="pt-3 border-t border-[#DEDAD0] space-y-2">
              <div className="flex items-center justify-between text-[11px] text-[#6B7280]">
                <span>Development Mode:</span>
                <span className="font-mono text-[#854D0E]">DEV_TEST_MODE=true</span>
              </div>
              <button
                type="button"
                onClick={handleDevLogin}
                disabled={devLoading}
                className="w-full rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] px-3 py-2 text-xs font-semibold text-[#242424] hover:bg-[#F7F4EB] transition-colors"
              >
                {devLoading ? 'Connecting Test Session...' : 'Sign in as Development Test User'}
              </button>
            </div>
          )}
          {/* Public Policy & Terms Footer */}
          <div className="pt-4 border-t border-[#DEDAD0] flex items-center justify-center gap-4 text-xs">
            <a
              href="/privacy"
              onClick={(e) => {
                e.preventDefault()
                if (onNavigate) onNavigate('/privacy')
                else window.location.href = '/privacy'
              }}
              className="text-[#4B5563] hover:text-[#242424] hover:underline transition-colors cursor-pointer"
            >
              Privacy Policy
            </a>
            <span className="text-[#DEDAD0]">•</span>
            <a
              href="/terms"
              onClick={(e) => {
                e.preventDefault()
                if (onNavigate) onNavigate('/terms')
                else window.location.href = '/terms'
              }}
              className="text-[#4B5563] hover:text-[#242424] hover:underline transition-colors cursor-pointer"
            >
              Terms of Service
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}
