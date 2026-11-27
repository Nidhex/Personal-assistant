import React, { useState, useEffect } from 'react'
import {
  LayoutDashboard,
  Mail,
  Calendar,
  CheckSquare,
  BookOpen,
  Compass,
  MessageSquare,
  Briefcase,
  ShieldAlert,
  Activity,
  Link2,
  Settings,
  Search,
  Bell,
  Menu,
  X,
  Power,
  ShieldCheck,
  RefreshCw,
  LogOut
} from 'lucide-react'

// Import API client (strict backend integration preserved)
import {
  checkAuthStatus,
  fetchCurrentUser,
  logoutUser,
  fetchUserData,
  fetchGmailMessages
} from './api'

// Import views
import LoginView from './views/LoginView'
import OverviewView from './views/OverviewView'
import InboxView from './views/InboxView'
import CalendarTasksView from './views/CalendarTasksView'
import ApprovalsView from './views/ApprovalsView'
import StudyView from './views/StudyView'
import PlanningView from './views/PlanningView'
import WorkspacesChatView from './views/WorkspacesChatView'
import ActivityTraceView from './views/ActivityTraceView'
import DailyDigestView from './views/DailyDigestView'
import AccountsSettingsView from './views/AccountsSettingsView'

export default function App() {
  const [authLoading, setAuthLoading] = useState(true)
  const [currentUser, setCurrentUser] = useState(null)
  const [gmailConnected, setGmailConnected] = useState(false)
  const [authStatus, setAuthStatus] = useState({ google_configured: false, dev_test_mode_enabled: false })
  const [authError, setAuthError] = useState(null)

  // Navigation
  const [activeTab, setActiveTab] = useState('overview')
  const [activeWorkspaceId, setActiveWorkspaceId] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const [toastMessage, setToastMessage] = useState(null)
  const [killSwitchActive, setKillSwitchActive] = useState(false)

  // Real Data State
  const [emails, setEmails] = useState([])
  const [calendarEvents, setCalendarEvents] = useState([])
  const [tasks, setTasks] = useState([])
  const [approvals, setApprovals] = useState([])
  const [workspaces, setWorkspaces] = useState([])
  const [traces, setTraces] = useState([])
  const [dailyDigest, setDailyDigest] = useState(null)

  const showToast = (msg) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(null), 3400)
  }

  // Check URL parameters for OAuth return
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('auth_error')) {
      setAuthError(params.get('auth_error'))
    }
    if (params.get('auth_success') || params.get('auth_error')) {
      window.history.replaceState({}, document.title, window.location.pathname)
    }
  }, [])

  // Check Auth on initial load
  const loadAuthAndUser = async () => {
    setAuthLoading(true)
    try {
      const [statusData, meData] = await Promise.all([
        checkAuthStatus(),
        fetchCurrentUser()
      ])

      setAuthStatus(statusData)

      if (meData.authenticated && meData.user) {
        setCurrentUser(meData.user)
        setGmailConnected(meData.gmail_connected)
        await loadRealUserData(meData.gmail_connected)
      } else {
        setCurrentUser(null)
        setGmailConnected(false)
      }
    } catch {
      setCurrentUser(null)
    } finally {
      setAuthLoading(false)
    }
  }

  const loadRealUserData = async (isGmailConnected) => {
    try {
      const userData = await fetchUserData()
      setTasks(userData.tasks || [])
      setWorkspaces(userData.workspaces || [])
      setApprovals(userData.approvals || [])
      setTraces(userData.activity || [])
      if (userData.calendar_events) {
        setCalendarEvents(userData.calendar_events.map(e => ({
          ...e,
          date: e.event_date,
          time: `${e.start_time} - ${e.end_time}`,
          startTime: e.start_time,
          endTime: e.end_time
        })))
      }
      if (userData.daily_digest) {
        setDailyDigest(userData.daily_digest)
      }
      if (userData.kill_switch_active !== undefined) {
        setKillSwitchActive(Boolean(userData.kill_switch_active))
      }

      if (isGmailConnected) {
        try {
          const mailData = await fetchGmailMessages(null, 15)
          if (mailData.connected) {
            setEmails(mailData.messages || [])
          }
        } catch {
          setEmails([])
        }
      } else {
        setEmails([])
      }
    } catch {
      // Retain clean empty structures
    }
  }

  useEffect(() => {
    loadAuthAndUser()
  }, [])

  const handleSignOut = async () => {
    await logoutUser()
    setCurrentUser(null)
    setGmailConnected(false)
    setEmails([])
    setTasks([])
    setWorkspaces([])
    setApprovals([])
    setTraces([])
    showToast('Signed out successfully.')
  }

  const handleGmailStatusChange = (status) => {
    setGmailConnected(status)
    if (status) {
      loadRealUserData(true)
    } else {
      setEmails([])
    }
  }

  // Task Toggle
  const toggleTask = (id) => {
    setTasks(prev =>
      prev.map(t => (t.id === id ? { ...t, completed: !t.completed } : t))
    )
  }

  const pendingApprovalsCount = approvals ? approvals.filter(a => a.status === 'pending').length : 0
  const unreadEmailsCount = emails ? emails.filter(e => e.isUnread).length : 0
  const pendingTasksCount = tasks ? tasks.filter(t => !t.completed).length : 0

  // Loading Screen in Warm Ivory / Minimal Style
  if (authLoading) {
    return (
      <div className="min-h-screen bg-[#F7F4EB] text-[#242424] flex items-center justify-center p-4">
        <div className="flex flex-col items-center gap-3.5 bg-[#FFFDF8] border border-[#DEDAD0] px-8 py-7 rounded-2xl shadow-warm">
          <RefreshCw className="h-5 w-5 animate-spin text-[#242424]" />
          <p className="text-xs font-medium tracking-wide text-[#737373]">
            Verifying authenticated session...
          </p>
        </div>
      </div>
    )
  }

  // Authentication Gate: Render LoginView if unauthenticated
  if (!currentUser) {
    return (
      <LoginView
        authStatus={authStatus}
        onAuthSuccess={loadAuthAndUser}
        showToast={showToast}
        authError={authError}
      />
    )
  }

  // Navigation Items according to Specification
  const navSections = [
    {
      heading: 'YOUR WORK',
      items: [
        { id: 'overview', label: 'Overview', icon: LayoutDashboard },
        { id: 'inbox', label: 'Inbox', icon: Mail, badge: unreadEmailsCount || null, badgeBg: 'bg-[#B9CDE7] text-[#171717]' },
        { id: 'calendar', label: 'Calendar', icon: Calendar },
        { id: 'tasks', label: 'Tasks', icon: CheckSquare, badge: pendingTasksCount || null, badgeBg: 'bg-[#E9DB91] text-[#171717]' },
        { id: 'study', label: 'Study', icon: BookOpen },
        { id: 'planning', label: 'Planning', icon: Compass }
      ]
    },
    {
      heading: 'WORKSPACES',
      items: [
        { id: 'main_chat', label: 'Main Chat', icon: MessageSquare },
        { id: 'workspaces', label: 'Workspaces', icon: Briefcase, badge: workspaces.length || null, badgeBg: 'bg-[#D5E0BD] text-[#171717]' }
      ]
    },
    {
      heading: 'REVIEW',
      items: [
        { id: 'digest', label: 'Daily Briefing', icon: Sparkles },
        {
          id: 'approvals',
          label: 'Approvals',
          icon: ShieldAlert,
          badge: pendingApprovalsCount > 0 ? pendingApprovalsCount : null,
          badgeBg: 'bg-[#EBC1D9] text-[#171717]'
        },
        { id: 'activity', label: 'Activity & Trace', icon: Activity }
      ]
    },
    {
      heading: 'PREFERENCES',
      items: [
        { id: 'accounts', label: 'Connected Accounts', icon: Link2 },
        { id: 'settings', label: 'Settings', icon: Settings }
      ]
    }
  ]

  const pageTitles = {
    overview: 'Overview',
    inbox: 'Inbox',
    calendar: 'Calendar',
    tasks: 'Tasks',
    study: 'Study & Notes',
    planning: 'Project Planning',
    main_chat: 'Assistant Chat',
    workspaces: 'Workspaces',
    digest: 'Daily Briefing & Agent Runs',
    approvals: 'Approvals Review',
    activity: 'Activity & Trace',
    accounts: 'Connected Accounts',
    settings: 'Settings & Profile'
  }

  return (
    <div className="flex min-h-screen bg-[#F7F4EB] text-[#242424] font-sans selection:bg-[#B9CDE7] selection:text-[#171717]">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2.5 rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] px-4 py-2.5 text-xs text-[#242424] shadow-warm-md animate-in fade-in slide-in-from-bottom-2 duration-200">
          <div className="h-2 w-2 rounded-full bg-[#708A4E]" />
          <span className="font-medium">{toastMessage}</span>
        </div>
      )}

      {/* Mobile Drawer Backdrop */}
      {isMobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-[#171717]/40 backdrop-blur-xs lg:hidden"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}

      {/* Fixed Deep Charcoal Vertical Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-[#262626] bg-[#171717] text-[#EDEDED] transition-transform duration-200 ease-in-out lg:static lg:translate-x-0 ${
          isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Neutral Header Branding */}
        <div className="flex h-16 items-center justify-between px-5 border-b border-[#262626]">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#242424] border border-[#333333] text-[#FFFDF8]">
              <ShieldCheck className="h-4 w-4 text-[#D5E0BD]" />
            </div>
            <div>
              <div className="text-xs font-semibold tracking-tight text-[#FFFDF8]">
                Personal Assistant
              </div>
              <div className="text-[10px] text-[#8E8E8E] font-medium tracking-wide">
                Supervised Workspace
              </div>
            </div>
          </div>

          <button
            onClick={() => setIsMobileMenuOpen(false)}
            className="rounded p-1 text-[#8E8E8E] hover:text-[#FFFDF8] lg:hidden"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Navigation Sections */}
        <div className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
          {navSections.map((section, sIdx) => (
            <div key={sIdx} className="space-y-1">
              <div className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-[#737373]">
                {section.heading}
              </div>

              {section.items.map((item) => {
                const Icon = item.icon
                const isActive = activeTab === item.id
                return (
                  <button
                    key={item.id}
                    onClick={() => {
                      setActiveTab(item.id)
                      setIsMobileMenuOpen(false)
                    }}
                    className={`group flex w-full items-center justify-between rounded-lg px-3 py-2 text-xs transition-all ${
                      isActive
                        ? 'bg-[#262626] text-[#FFFDF8] font-medium border border-[#383838]'
                        : 'text-[#9CA3AF] hover:bg-[#202020] hover:text-[#F3F4F6]'
                    }`}
                  >
                    <div className="flex items-center gap-2.5">
                      <Icon
                        className={`h-4 w-4 transition-colors ${
                          isActive ? 'text-[#FFFDF8]' : 'text-[#737373] group-hover:text-[#A3A3A3]'
                        }`}
                      />
                      <span>{item.label}</span>
                    </div>

                    {item.badge && (
                      <span
                        className={`flex h-4 min-w-4 items-center justify-center rounded px-1.5 text-[10px] font-medium ${
                          item.badgeBg || 'bg-[#2A2A2A] text-[#E5E5E5]'
                        }`}
                      >
                        {item.badge}
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          ))}
        </div>

        {/* Sidebar Footer: Engine Status & User Profile */}
        <div className="border-t border-[#262626] p-3 space-y-2 bg-[#141414]">
          {/* Supervision Mode & Kill Switch Pill */}
          <div className="flex items-center justify-between px-2.5 py-1.5 rounded-lg border border-[#262626] bg-[#1C1C1C]">
            <div className="flex items-center gap-2">
              <span
                className={`h-2 w-2 rounded-full ${
                  killSwitchActive ? 'bg-[#EF4444] animate-pulse' : 'bg-[#D5E0BD]'
                }`}
              />
              <span className="text-[11px] font-medium text-[#A3A3A3]">
                {killSwitchActive ? 'Engine Halted' : 'Supervised'}
              </span>
            </div>

            <button
              onClick={() => {
                const next = !killSwitchActive
                setKillSwitchActive(next)
                showToast(next ? 'Emergency kill switch engaged.' : 'Assistant engine resumed.')
              }}
              title={killSwitchActive ? 'Resume Engine' : 'Trigger Kill Switch'}
              className={`p-1 rounded text-xs transition-colors ${
                killSwitchActive ? 'text-[#D5E0BD] hover:text-[#E8F0D6]' : 'text-[#737373] hover:text-[#EF4444]'
              }`}
            >
              <Power className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* User Profile Card */}
          <div className="flex items-center justify-between rounded-lg p-2 hover:bg-[#202020] transition-colors">
            <button
              onClick={() => setActiveTab('settings')}
              className="flex items-center gap-2.5 min-w-0 text-left flex-1"
            >
              {currentUser.picture ? (
                <img
                  src={currentUser.picture}
                  alt={currentUser.name}
                  className="h-7 w-7 rounded-full border border-[#333333] shrink-0 object-cover"
                />
              ) : (
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#2A2A2A] text-xs font-semibold text-[#E5E5E5] border border-[#333333]">
                  {currentUser.name ? currentUser.name[0].toUpperCase() : 'U'}
                </div>
              )}
              <div className="min-w-0">
                <div className="text-xs font-medium text-[#EDEDED] truncate">{currentUser.name}</div>
                <div className="text-[10px] text-[#8E8E8E] truncate">{currentUser.email}</div>
              </div>
            </button>

            <button
              onClick={handleSignOut}
              title="Sign out"
              className="p-1.5 text-[#737373] hover:text-[#EF4444] rounded transition-colors"
            >
              <LogOut className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden min-w-0">
        {/* Top Header */}
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-[#DEDAD0] bg-[#FFFDF8]/90 px-4 sm:px-6 lg:px-8 backdrop-blur-md">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setIsMobileMenuOpen(true)}
              className="rounded-lg p-1.5 text-[#737373] hover:bg-[#F7F4EB] hover:text-[#242424] lg:hidden"
            >
              <Menu className="h-5 w-5" />
            </button>

            <div>
              <h1 className="text-sm font-semibold tracking-tight text-[#242424]">
                {pageTitles[activeTab] || activeTab}
              </h1>
            </div>
          </div>

          {/* Right Header Controls */}
          <div className="flex items-center gap-3">
            {/* Quick Search */}
            <div className="relative hidden sm:block w-48 md:w-60">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[#9CA3AF]" />
              <input
                type="text"
                placeholder="Search..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full rounded-lg border border-[#DEDAD0] bg-[#F7F4EB] py-1.5 pl-9 pr-7 text-xs text-[#242424] placeholder:text-[#9CA3AF] focus:border-[#242424] focus:bg-[#FFFDF8] focus:outline-none transition-all"
              />
              <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[10px] font-medium text-[#9CA3AF] border border-[#DEDAD0] rounded px-1 bg-[#FFFDF8]">
                /
              </span>
            </div>

            {/* Approvals Notification Bell */}
            <button
              onClick={() => {
                setActiveTab('approvals')
                showToast(`You have ${pendingApprovalsCount} action items awaiting approval.`)
              }}
              className="relative rounded-lg border border-[#DEDAD0] bg-[#FFFDF8] p-2 text-[#737373] hover:text-[#242424] hover:border-[#242424] transition-colors"
              title="Approvals and alerts"
            >
              <Bell className="h-4 w-4" />
              {pendingApprovalsCount > 0 && (
                <span className="absolute -top-1 -right-1 flex h-2.5 w-2.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#EBC1D9] opacity-75" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-[#EBC1D9] border border-[#FFFDF8]" />
                </span>
              )}
            </button>

            {/* Gmail Connection Status Pill */}
            <div className="hidden sm:flex items-center gap-1.5 pl-3 border-l border-[#DEDAD0]">
              <span
                className={`h-2 w-2 rounded-full ${
                  gmailConnected ? 'bg-[#708A4E]' : 'bg-[#D1D5DB]'
                }`}
              />
              <span className="text-[11px] font-medium text-[#6B7280]">
                {gmailConnected ? 'Gmail Synced' : 'Gmail Off'}
              </span>
            </div>
          </div>
        </header>

        {/* Dynamic View Mount */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 bg-[#F7F4EB]">
          <div className="mx-auto max-w-6xl">
            {activeTab === 'overview' && (
              <OverviewView
                emails={emails}
                gmailConnected={gmailConnected}
                tasks={tasks}
                toggleTask={toggleTask}
                approvals={approvals}
                calendarEvents={calendarEvents}
                dailyDigest={dailyDigest}
                activities={traces}
                killSwitchActive={killSwitchActive}
                setKillSwitchActive={setKillSwitchActive}
                setActiveTab={setActiveTab}
                showToast={showToast}
                currentUser={currentUser}
              />
            )}

            {activeTab === 'inbox' && (
              <InboxView
                currentUser={currentUser}
                gmailConnected={gmailConnected}
                onGmailStatusChange={handleGmailStatusChange}
                showToast={showToast}
                onTaskCreated={() => loadRealUserData(gmailConnected)}
              />
            )}

            {activeTab === 'calendar' && (
              <CalendarTasksView
                calendarEvents={calendarEvents}
                setCalendarEvents={setCalendarEvents}
                tasks={tasks}
                currentUser={currentUser}
                onTasksChanged={() => loadRealUserData(gmailConnected)}
                showToast={showToast}
                setActiveTab={setActiveTab}
                activeSubtab="calendar"
              />
            )}

            {activeTab === 'tasks' && (
              <CalendarTasksView
                calendarEvents={calendarEvents}
                setCalendarEvents={setCalendarEvents}
                tasks={tasks}
                currentUser={currentUser}
                onTasksChanged={() => loadRealUserData(gmailConnected)}
                showToast={showToast}
                setActiveTab={setActiveTab}
                activeSubtab="tasks_only"
              />
            )}

            {activeTab === 'study' && (
              <StudyView
                onTaskCreated={() => loadRealUserData(gmailConnected)}
                tasks={tasks}
                currentUser={currentUser}
                showToast={showToast}
                setActiveTab={setActiveTab}
              />
            )}

            {activeTab === 'planning' && (
              <PlanningView
                setTasks={setTasks}
                showToast={showToast}
                setActiveTab={setActiveTab}
              />
            )}

            {activeTab === 'main_chat' && (
              <WorkspacesChatView
                workspaces={workspaces}
                onWorkspacesChanged={() => loadRealUserData(gmailConnected)}
                isMainChatOnly={true}
                killSwitchActive={killSwitchActive}
                showToast={showToast}
              />
            )}

            {activeTab === 'workspaces' && (
              <WorkspacesChatView
                workspaces={workspaces}
                onWorkspacesChanged={() => loadRealUserData(gmailConnected)}
                activeWorkspaceId={activeWorkspaceId}
                setActiveWorkspaceId={setActiveWorkspaceId}
                isMainChatOnly={false}
                killSwitchActive={killSwitchActive}
                showToast={showToast}
              />
            )}

            {activeTab === 'digest' && (
              <DailyDigestView
                showToast={showToast}
                currentUser={currentUser}
                killSwitchActive={killSwitchActive}
                setKillSwitchActive={setKillSwitchActive}
                setActiveTab={setActiveTab}
              />
            )}

            {activeTab === 'approvals' && (
              <ApprovalsView
                approvals={approvals}
                onApprovalsChanged={() => loadRealUserData(gmailConnected)}
                showToast={showToast}
              />
            )}

            {activeTab === 'activity' && (
              <ActivityTraceView
                traces={traces}
                dailyDigest={dailyDigest}
                killSwitchActive={killSwitchActive}
                setKillSwitchActive={setKillSwitchActive}
                showToast={showToast}
              />
            )}

            {activeTab === 'accounts' && (
              <AccountsSettingsView
                currentUser={currentUser}
                gmailConnected={gmailConnected}
                onGmailStatusChange={handleGmailStatusChange}
                onSignOut={handleSignOut}
                showToast={showToast}
                defaultTab="accounts"
              />
            )}

            {activeTab === 'settings' && (
              <AccountsSettingsView
                currentUser={currentUser}
                gmailConnected={gmailConnected}
                onGmailStatusChange={handleGmailStatusChange}
                onSignOut={handleSignOut}
                showToast={showToast}
                defaultTab="profile"
              />
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
