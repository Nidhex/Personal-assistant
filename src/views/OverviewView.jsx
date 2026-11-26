import React, { useState } from 'react'
import {
  ShieldAlert,
  ArrowRight,
  Mail,
  CheckCircle2,
  Send,
  Power,
  Clock,
  Calendar,
  CheckSquare,
  AlertTriangle,
  Sparkles,
  FileText,
  UserCheck
} from 'lucide-react'

export default function OverviewView({
  emails = [],
  gmailConnected = false,
  tasks = [],
  toggleTask,
  approvals = [],
  dailyDigest = null,
  activities = [],
  killSwitchActive = false,
  setKillSwitchActive,
  setActiveTab,
  showToast,
  currentUser = null
}) {
  const [quickPrompt, setQuickPrompt] = useState('')

  const handlePromptSubmit = (e) => {
    e.preventDefault()
    if (!quickPrompt.trim()) return
    if (killSwitchActive) {
      showToast('Action blocked: Assistant engine is halted by the emergency kill switch.')
      return
    }
    const val = quickPrompt
    setQuickPrompt('')
    showToast(`Request received: "${val.length > 30 ? val.substring(0, 30) + '...' : val}"`)
    setActiveTab('main_chat')
  }

  const pendingApprovals = approvals ? approvals.filter(a => a.status === 'pending') : []
  const unreadEmails = emails ? emails.filter(e => e.isUnread) : []
  const pendingTasks = tasks ? tasks.filter(t => !t.completed) : []
  const recentTraces = activities ? activities.slice(0, 5) : []

  // Greeting determination
  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'
  const displayName = currentUser?.name ? currentUser.name.split(' ')[0] : 'there'

  return (
    <div className="space-y-7">
      {/* Greeting & Date Header */}
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-2 border-b border-[#DEDAD0] pb-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-[#242424]">
            {greeting}, {displayName}
          </h1>
          <p className="text-xs text-[#6B7280] mt-0.5">
            Here is your daily workspace briefing and supervisory overview.
          </p>
        </div>

        <div className="text-xs font-medium text-[#6B7280] font-mono">
          {new Date().toLocaleDateString('en-US', {
            weekday: 'long',
            month: 'short',
            day: 'numeric'
          })}
        </div>
      </div>

      {/* Emergency Kill Switch Status Banner */}
      {killSwitchActive && (
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 rounded-xl border border-[#EBC1D9] bg-[#FFFDF8] px-5 py-3.5 shadow-warm-sm">
          <div className="flex items-center gap-3">
            <span className="h-2.5 w-2.5 rounded-full bg-[#EF4444] animate-ping" />
            <div>
              <div className="text-xs font-semibold text-[#B91C1C]">
                Assistant Engine Halted (Emergency Kill Switch Engaged)
              </div>
              <div className="text-[11px] text-[#6B7280]">
                All automated background tasks, tool calls, and integrations are paused.
              </div>
            </div>
          </div>

          <button
            onClick={() => {
              setKillSwitchActive(false)
              showToast('Assistant engine resumed.')
            }}
            className="rounded-lg border border-[#DEDAD0] bg-[#F7F4EB] px-3.5 py-1.5 text-xs font-semibold text-[#242424] hover:bg-[#FFFDF8] transition-colors"
          >
            Resume Engine
          </button>
        </div>
      )}

      {/* Natural Chat Entry Area */}
      <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-4 sm:p-5 shadow-warm-sm">
        <form onSubmit={handlePromptSubmit} className="space-y-3">
          <div className="flex items-center justify-between text-xs text-[#6B7280]">
            <span className="font-medium text-[#242424] flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5 text-[#242424]" />
              How can I assist your workflow today?
            </span>
            <span className="text-[11px] font-mono text-[#6B7280]">Supervised Mode</span>
          </div>

          <div className="relative">
            <input
              type="text"
              value={quickPrompt}
              disabled={killSwitchActive}
              onChange={(e) => setQuickPrompt(e.target.value)}
              placeholder="Ask anything or request an action (e.g. summarize unread emails, check tasks...)"
              className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] px-4 py-3 text-xs text-[#242424] placeholder:text-[#9CA3AF] focus:border-[#242424] focus:bg-[#FFFDF8] focus:outline-none transition-all disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!quickPrompt.trim() || killSwitchActive}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg bg-[#242424] px-3.5 py-1.5 text-xs font-semibold text-[#FFFDF8] hover:bg-[#383838] disabled:opacity-30 transition-all flex items-center gap-1.5 cursor-pointer"
            >
              <span>Ask</span>
              <Send className="h-3 w-3" />
            </button>
          </div>
        </form>
      </div>

      {/* Attention Grid: Items Needing Attention with Pastel Categorization */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {/* Approvals Needed (Soft Pink Accent) */}
        <div
          onClick={() => setActiveTab('approvals')}
          className="rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] p-4 hover:border-[#242424] transition-all cursor-pointer shadow-warm-sm flex flex-col justify-between"
        >
          <div className="flex items-start justify-between">
            <span className="inline-flex items-center gap-1.5 rounded-md bg-[#EBC1D9]/50 border border-[#EBC1D9] px-2 py-0.5 text-[11px] font-semibold text-[#171717]">
              <ShieldAlert className="h-3 w-3" />
              Approvals
            </span>
            <span className="text-lg font-bold font-mono text-[#242424]">
              {pendingApprovals.length}
            </span>
          </div>
          <div className="mt-3">
            <p className="text-xs text-[#242424] font-medium">
              {pendingApprovals.length === 0
                ? 'No actions pending review'
                : `${pendingApprovals.length} action item(s) awaiting approval`}
            </p>
            <p className="text-[11px] text-[#6B7280] mt-0.5">
              Requires explicit user sign-off
            </p>
          </div>
        </div>

        {/* Action Items / Tasks (Muted Yellow Accent) */}
        <div
          onClick={() => setActiveTab('tasks')}
          className="rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] p-4 hover:border-[#242424] transition-all cursor-pointer shadow-warm-sm flex flex-col justify-between"
        >
          <div className="flex items-start justify-between">
            <span className="inline-flex items-center gap-1.5 rounded-md bg-[#E9DB91]/50 border border-[#E9DB91] px-2 py-0.5 text-[11px] font-semibold text-[#171717]">
              <CheckSquare className="h-3 w-3" />
              Active Tasks
            </span>
            <span className="text-lg font-bold font-mono text-[#242424]">
              {pendingTasks.length}
            </span>
          </div>
          <div className="mt-3">
            <p className="text-xs text-[#242424] font-medium">
              {pendingTasks.length === 0
                ? 'All tasks completed'
                : `${pendingTasks.length} pending task(s)`}
            </p>
            <p className="text-[11px] text-[#6B7280] mt-0.5">
              Synced from inbox & schedule
            </p>
          </div>
        </div>

        {/* Gmail Inbox (Soft Blue Accent) */}
        <div
          onClick={() => setActiveTab('inbox')}
          className="rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] p-4 hover:border-[#242424] transition-all cursor-pointer shadow-warm-sm flex flex-col justify-between"
        >
          <div className="flex items-start justify-between">
            <span className="inline-flex items-center gap-1.5 rounded-md bg-[#B9CDE7]/50 border border-[#B9CDE7] px-2 py-0.5 text-[11px] font-semibold text-[#171717]">
              <Mail className="h-3 w-3" />
              Inbox
            </span>
            <span className="text-lg font-bold font-mono text-[#242424]">
              {gmailConnected ? unreadEmails.length : '—'}
            </span>
          </div>
          <div className="mt-3">
            <p className="text-xs text-[#242424] font-medium">
              {gmailConnected
                ? `${unreadEmails.length} unread message(s)`
                : 'Gmail disconnected'}
            </p>
            <p className="text-[11px] text-[#6B7280] mt-0.5">
              {gmailConnected ? 'Read-only access active' : 'Click to connect Google account'}
            </p>
          </div>
        </div>
      </div>

      {/* Main Split Content: Real Inbox Preview & Real Tasks List */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Real Inbox Section */}
        <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-[#DEDAD0]">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-[#B9CDE7]" />
                <h3 className="text-xs font-semibold uppercase tracking-wider text-[#242424]">
                  Recent Emails
                </h3>
              </div>
              <button
                onClick={() => setActiveTab('inbox')}
                className="text-[11px] font-medium text-[#6B7280] hover:text-[#242424] flex items-center gap-1"
              >
                <span>View Inbox</span>
                <ArrowRight className="h-3 w-3" />
              </button>
            </div>

            <div className="mt-3 divide-y divide-[#DEDAD0]">
              {!gmailConnected ? (
                <div className="py-8 text-center text-xs text-[#6B7280] space-y-2">
                  <Mail className="mx-auto h-6 w-6 text-[#9CA3AF]" />
                  <p>Connect your Google account to read your real Gmail messages.</p>
                  <button
                    onClick={() => setActiveTab('inbox')}
                    className="mt-1 rounded-lg border border-[#DEDAD0] bg-[#F7F4EB] px-3 py-1.5 text-xs font-semibold text-[#242424] hover:bg-[#EFECE2]"
                  >
                    Connect Gmail
                  </button>
                </div>
              ) : emails.length === 0 ? (
                <div className="py-8 text-center text-xs text-[#6B7280]">
                  Your inbox has no messages right now.
                </div>
              ) : (
                emails.slice(0, 4).map((email) => (
                  <div
                    key={email.id}
                    onClick={() => setActiveTab('inbox')}
                    className="py-3 first:pt-1 last:pb-1 cursor-pointer hover:bg-[#F7F4EB]/60 px-2 -mx-2 rounded-lg transition-colors"
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        {email.isUnread && (
                          <span className="h-1.5 w-1.5 rounded-full bg-[#3B82F6] shrink-0" />
                        )}
                        <span className={`text-xs truncate ${email.isUnread ? 'font-semibold text-[#242424]' : 'text-[#6B7280]'}`}>
                          {email.senderName || email.from}
                        </span>
                      </div>
                      <span className="text-[10px] text-[#9CA3AF] font-mono shrink-0">
                        {email.date ? email.date.split(' ').slice(0, 3).join(' ') : ''}
                      </span>
                    </div>
                    <div className="text-xs font-medium text-[#242424] truncate mt-0.5">
                      {email.subject || '(No subject)'}
                    </div>
                    <p className="text-[11px] text-[#6B7280] line-clamp-1 mt-0.5">
                      {email.snippet}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Real Tasks Checklist Section */}
        <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-[#DEDAD0]">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-[#E9DB91]" />
                <h3 className="text-xs font-semibold uppercase tracking-wider text-[#242424]">
                  Today's Tasks
                </h3>
              </div>
              <button
                onClick={() => setActiveTab('tasks')}
                className="text-[11px] font-medium text-[#6B7280] hover:text-[#242424] flex items-center gap-1"
              >
                <span>All Tasks ({tasks.length})</span>
                <ArrowRight className="h-3 w-3" />
              </button>
            </div>

            <div className="mt-3 divide-y divide-[#DEDAD0]">
              {tasks.length === 0 ? (
                <div className="py-8 text-center text-xs text-[#6B7280]">
                  No tasks currently recorded. Create tasks or extract them from emails.
                </div>
              ) : (
                tasks.slice(0, 5).map((task) => (
                  <div
                    key={task.id}
                    className="py-2.5 flex items-start gap-3 hover:bg-[#F7F4EB]/60 px-2 -mx-2 rounded-lg transition-colors"
                  >
                    <input
                      type="checkbox"
                      checked={!!task.completed}
                      onChange={() => toggleTask && toggleTask(task.id)}
                      className="mt-0.5 h-4 w-4 rounded border-[#DEDAD0] text-[#242424] accent-[#242424] cursor-pointer"
                    />
                    <div className="min-w-0 flex-1">
                      <div
                        className={`text-xs ${
                          task.completed
                            ? 'line-through text-[#9CA3AF]'
                            : 'font-medium text-[#242424]'
                        }`}
                      >
                        {task.title}
                      </div>
                      <div className="flex items-center gap-2 mt-0.5 text-[10px] text-[#6B7280]">
                        <span className="font-mono">{task.due_date || task.dueDate || 'No due date'}</span>
                        {task.priority === 'high' && (
                          <span className="rounded bg-[#EBC1D9]/60 px-1.5 py-0.2 text-[9px] font-semibold text-[#171717]">
                            High Priority
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Actual Pending Approvals Table Section (if any exist) */}
      {pendingApprovals.length > 0 && (
        <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm">
          <div className="flex items-center justify-between pb-3 border-b border-[#DEDAD0]">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-[#EBC1D9]" />
              <h3 className="text-xs font-semibold uppercase tracking-wider text-[#242424]">
                Pending Human Authorizations ({pendingApprovals.length})
              </h3>
            </div>
            <button
              onClick={() => setActiveTab('approvals')}
              className="text-[11px] font-semibold text-[#242424] hover:underline"
            >
              Open Approvals Workspace
            </button>
          </div>

          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-[#DEDAD0] text-[11px] text-[#6B7280]">
                  <th className="pb-2 font-medium">Action Type</th>
                  <th className="pb-2 font-medium">Target</th>
                  <th className="pb-2 font-medium">Subject</th>
                  <th className="pb-2 font-medium">Trigger Reason</th>
                  <th className="pb-2 font-medium text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#DEDAD0]">
                {pendingApprovals.slice(0, 3).map((item) => (
                  <tr key={item.id} className="text-[#242424]">
                    <td className="py-2.5 font-medium">
                      <span className="rounded bg-[#F7F4EB] border border-[#DEDAD0] px-2 py-0.5 text-[10px] font-mono">
                        {item.type}
                      </span>
                    </td>
                    <td className="py-2.5 text-[#6B7280] font-mono text-[11px]">{item.target}</td>
                    <td className="py-2.5 font-medium">{item.subject}</td>
                    <td className="py-2.5 text-[#6B7280]">{item.reason}</td>
                    <td className="py-2.5 text-right">
                      <button
                        onClick={() => setActiveTab('approvals')}
                        className="rounded-lg border border-[#DEDAD0] bg-[#F7F4EB] px-2.5 py-1 text-[11px] font-semibold text-[#242424] hover:bg-[#EFECE2]"
                      >
                        Review
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Recent Agent Activity Timeline */}
      <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm">
        <div className="flex items-center justify-between pb-3 border-b border-[#DEDAD0]">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-[#D5E0BD]" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[#242424]">
              Recent Activity & Supervisory Audit
            </h3>
          </div>
          <button
            onClick={() => setActiveTab('activity')}
            className="text-[11px] font-medium text-[#6B7280] hover:text-[#242424] flex items-center gap-1"
          >
            <span>Full Trace Log</span>
            <ArrowRight className="h-3 w-3" />
          </button>
        </div>

        <div className="mt-3">
          {recentTraces.length === 0 ? (
            <p className="py-6 text-center text-xs text-[#6B7280]">
              No assistant activity recorded yet. Run tasks or chat to see real execution logs.
            </p>
          ) : (
            <div className="space-y-2.5">
              {recentTraces.map((trace) => (
                <div
                  key={trace.id}
                  className="flex items-center justify-between p-2.5 rounded-lg border border-[#DEDAD0] bg-[#F7F4EB]/50 text-xs"
                >
                  <div className="flex items-center gap-3">
                    <span className="h-2 w-2 rounded-full bg-[#708A4E]" />
                    <div>
                      <div className="font-medium text-[#242424]">{trace.trigger}</div>
                      <div className="text-[11px] text-[#6B7280]">{trace.action}</div>
                    </div>
                  </div>
                  <span className="text-[10px] text-[#9CA3AF] font-mono">{trace.timestamp}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
