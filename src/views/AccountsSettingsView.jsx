import React, { useState } from 'react'
import {
  Lock,
  CheckCircle2,
  XCircle,
  LogOut
} from 'lucide-react'
import { disconnectGmail, getGoogleAuthUrl } from '../api'

export default function AccountsSettingsView({
  currentUser,
  gmailConnected,
  onGmailStatusChange,
  onSignOut,
  showToast,
  defaultTab = 'accounts'
}) {
  const [activeTab, setActiveTab] = useState(defaultTab)
  const [disconnecting, setDisconnecting] = useState(false)

  const handleDisconnect = async () => {
    if (!window.confirm('Are you sure you want to disconnect Gmail access?')) return
    setDisconnecting(true)
    try {
      await disconnectGmail()
      onGmailStatusChange(false)
      showToast('Gmail account disconnected and session token revoked.')
    } catch (err) {
      showToast(err.message || 'Failed to disconnect Gmail.')
    } finally {
      setDisconnecting(false)
    }
  }

  const handleConnectGmail = async () => {
    try {
      const data = await getGoogleAuthUrl()
      if (data.auth_url) window.location.href = data.auth_url
    } catch (err) {
      showToast(err.message || 'Failed to initiate Google OAuth.')
    }
  }

  return (
    <div className="space-y-6">
      {/* Header & Sub-Tab Switcher */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#DEDAD0] pb-4">
        <div>
          <h2 className="text-base font-semibold text-[#242424]">Preferences & Governance</h2>
          <p className="text-xs text-[#6B7280] mt-0.5">
            Manage authenticated integration boundaries, supervisory policies, and active user profile.
          </p>
        </div>

        <div className="flex items-center gap-1 rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] p-1 text-xs shadow-warm-sm">
          <button
            onClick={() => setActiveTab('accounts')}
            className={`rounded-lg px-3 py-1 font-medium transition-colors cursor-pointer ${
              activeTab === 'accounts' ? 'bg-[#242424] text-[#FFFDF8]' : 'text-[#6B7280] hover:text-[#242424]'
            }`}
          >
            Connected Accounts
          </button>
          <button
            onClick={() => setActiveTab('profile')}
            className={`rounded-lg px-3 py-1 font-medium transition-colors cursor-pointer ${
              activeTab === 'profile' ? 'bg-[#242424] text-[#FFFDF8]' : 'text-[#6B7280] hover:text-[#242424]'
            }`}
          >
            User Profile
          </button>
          <button
            onClick={() => setActiveTab('policies')}
            className={`rounded-lg px-3 py-1 font-medium transition-colors cursor-pointer ${
              activeTab === 'policies' ? 'bg-[#242424] text-[#FFFDF8]' : 'text-[#6B7280] hover:text-[#242424]'
            }`}
          >
            Policies & Safeguards
          </button>
        </div>
      </div>

      {/* Security Isolation Notice */}
      <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-4 shadow-warm-sm flex items-start gap-3">
        <Lock className="h-4 w-4 text-[#242424] shrink-0 mt-0.5" />
        <div className="text-xs space-y-0.5">
          <span className="font-semibold text-[#242424]">Token & Credential Security Guarantee</span>
          <p className="text-[#6B7280]">
            Never enter raw passwords or tokens into chat. OAuth credentials and tokens are encrypted at rest with AES-256 Fernet and isolated strictly on the backend.
          </p>
        </div>
      </div>

      {/* Tab 1: Connected Accounts */}
      {activeTab === 'accounts' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Google Workspace Card */}
            <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm space-y-4 flex flex-col justify-between">
              <div className="space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-[#242424]">Google Workspace (Gmail)</h3>
                    <p className="text-[11px] text-[#6B7280] font-mono mt-0.5">
                      {gmailConnected ? currentUser?.email : 'Not Connected'}
                    </p>
                  </div>

                  <span
                    className={`rounded px-2 py-0.5 text-[10px] font-mono font-medium border ${
                      gmailConnected
                        ? 'border-[#D5E0BD] bg-[#D5E0BD]/50 text-[#171717]'
                        : 'border-[#DEDAD0] bg-[#F7F4EB] text-[#6B7280]'
                    }`}
                  >
                    {gmailConnected ? 'Connected & Read-Only' : 'Disconnected'}
                  </span>
                </div>

                {/* Granted Permissions */}
                <div className="space-y-1.5 text-xs">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-[#6B7280]">
                    Granted Scopes:
                  </span>
                  {gmailConnected ? (
                    <ul className="space-y-1 text-[#4B5563]">
                      <li className="flex items-start gap-1.5 text-[11px]">
                        <CheckCircle2 className="h-3.5 w-3.5 text-[#242424] shrink-0 mt-0.5" />
                        <span>Identity (openid, email, profile)</span>
                      </li>
                      <li className="flex items-start gap-1.5 text-[11px]">
                        <CheckCircle2 className="h-3.5 w-3.5 text-[#242424] shrink-0 mt-0.5" />
                        <span>Gmail: read-only message inspection (gmail.readonly)</span>
                      </li>
                    </ul>
                  ) : (
                    <p className="text-[11px] text-[#9CA3AF] italic">No active Google connection.</p>
                  )}
                </div>

                {/* Disabled / Blocked Permissions */}
                <div className="space-y-1.5 text-xs pt-1">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-[#991B1B]">
                    Strictly Blocked / Disabled:
                  </span>
                  <ul className="space-y-1 text-[#6B7280]">
                    <li className="flex items-start gap-1.5 text-[11px]">
                      <XCircle className="h-3.5 w-3.5 text-[#991B1B] shrink-0 mt-0.5" />
                      <span>Direct email sending (Disabled)</span>
                    </li>
                    <li className="flex items-start gap-1.5 text-[11px]">
                      <XCircle className="h-3.5 w-3.5 text-[#991B1B] shrink-0 mt-0.5" />
                      <span>Modify, delete or label emails (Disabled)</span>
                    </li>
                  </ul>
                </div>
              </div>

              {/* Action Button */}
              <div className="pt-3 border-t border-[#DEDAD0]">
                {gmailConnected ? (
                  <button
                    onClick={handleDisconnect}
                    disabled={disconnecting}
                    className="w-full rounded-xl border border-[#EBC1D9] bg-[#EBC1D9]/30 py-2 text-xs font-semibold text-[#171717] hover:bg-[#EBC1D9]/60 transition-colors cursor-pointer"
                  >
                    {disconnecting ? 'Revoking Access...' : 'Disconnect Gmail Account'}
                  </button>
                ) : (
                  <button
                    onClick={handleConnectGmail}
                    className="w-full rounded-xl bg-[#242424] py-2 text-xs font-semibold text-[#FFFDF8] hover:bg-[#383838] transition-colors cursor-pointer"
                  >
                    Connect Google Account
                  </button>
                )}
              </div>
            </div>

            {/* Local Sandbox Boundary Card */}
            <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm space-y-4 flex flex-col justify-between">
              <div className="space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-[#242424]">Local Knowledge Sandbox</h3>
                    <p className="text-[11px] text-[#6B7280] font-mono mt-0.5">Local Storage Directory</p>
                  </div>
                  <span className="rounded bg-[#D5E0BD]/50 border border-[#D5E0BD] px-2 py-0.5 text-[10px] font-mono font-medium text-[#171717]">
                    Active Sandbox
                  </span>
                </div>

                <div className="space-y-1.5 text-xs">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-[#6B7280]">
                    Local Boundaries:
                  </span>
                  <ul className="space-y-1 text-[#4B5563]">
                    <li className="flex items-start gap-1.5 text-[11px]">
                      <CheckCircle2 className="h-3.5 w-3.5 text-[#242424] shrink-0 mt-0.5" />
                      <span>Workspace document isolation enforced</span>
                    </li>
                    <li className="flex items-start gap-1.5 text-[11px]">
                      <CheckCircle2 className="h-3.5 w-3.5 text-[#242424] shrink-0 mt-0.5" />
                      <span>Zero cross-project data leakage without manual export</span>
                    </li>
                  </ul>
                </div>
              </div>

              <div className="pt-3 border-t border-[#DEDAD0] text-[11px] text-[#6B7280] font-mono">
                Boundary: Subsystem Sandbox
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: User Profile */}
      {activeTab === 'profile' && (
        <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-6 shadow-warm-sm space-y-6 max-w-xl">
          <div className="flex items-center gap-4">
            {currentUser?.picture ? (
              <img
                src={currentUser.picture}
                alt={currentUser.name}
                className="h-14 w-14 rounded-full border border-[#DEDAD0] object-cover"
              />
            ) : (
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-[#242424] text-base font-bold text-[#FFFDF8]">
                {currentUser?.name ? currentUser.name[0].toUpperCase() : 'U'}
              </div>
            )}
            <div>
              <h3 className="text-base font-semibold text-[#242424]">{currentUser?.name}</h3>
              <p className="text-xs text-[#6B7280] font-mono">{currentUser?.email}</p>
              <div className="flex items-center gap-2 mt-1">
                <span className="rounded bg-[#D5E0BD]/50 border border-[#D5E0BD] px-2 py-0.5 text-[10px] font-mono text-[#171717]">
                  Authenticated Session
                </span>
              </div>
            </div>
          </div>

          <div className="pt-4 border-t border-[#DEDAD0] space-y-3">
            <h4 className="text-xs font-semibold text-[#242424]">Active Session Controls</h4>
            <button
              onClick={onSignOut}
              className="rounded-xl border border-[#EBC1D9] bg-[#EBC1D9]/30 px-4 py-2 text-xs font-semibold text-[#171717] hover:bg-[#EBC1D9]/60 transition-colors flex items-center gap-2 cursor-pointer"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span>Sign Out of Personal Assistant</span>
            </button>
          </div>
        </div>
      )}

      {/* Tab 3: Supervisory Policies */}
      {activeTab === 'policies' && (
        <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-6 shadow-warm-sm space-y-4">
          <h3 className="text-sm font-semibold text-[#242424]">Supervisory Engine Policy Rules</h3>
          <div className="space-y-3 text-xs text-[#4B5563]">
            <div className="p-3.5 rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] space-y-1">
              <span className="font-semibold text-[#242424]">1. Human Sign-Off for Outbound Communications</span>
              <p className="text-[#6B7280]">
                All draft replies, emails, and external communications require explicit user verification in the Approvals tab.
              </p>
            </div>
            <div className="p-3.5 rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] space-y-1">
              <span className="font-semibold text-[#242424]">2. Read-Only Gmail Boundary</span>
              <p className="text-[#6B7280]">
                Access to Gmail is restricted to reading and searching email threads. The assistant cannot send, edit, or delete messages on your behalf.
              </p>
            </div>
            <div className="p-3.5 rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] space-y-1">
              <span className="font-semibold text-[#242424]">3. Complete Trace Auditability</span>
              <p className="text-[#6B7280]">
                Every tool execution, email query, and task creation event is permanently timestamped and logged in the Activity & Trace dashboard.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
