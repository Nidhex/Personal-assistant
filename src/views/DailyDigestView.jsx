import React, { useState, useEffect } from 'react'
import {
  Sparkles,
  Play,
  Clock,
  Calendar,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ShieldAlert,
  Power,
  RefreshCw,
  Mail,
  CheckSquare,
  FileText,
  ChevronDown,
  ChevronRight,
  Settings,
  History,
  Lock,
  ArrowRight
} from 'lucide-react'
import {
  fetchAgentSettings,
  updateAgentSettings,
  setKillSwitchApi,
  triggerManualAgentRun,
  fetchAgentRuns,
  fetchAgentRunSteps,
  fetchLatestDailyDigest
} from '../api'

const COMMON_TIMEZONES = [
  'UTC',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'Europe/London',
  'Europe/Paris',
  'Asia/Kolkata',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Australia/Sydney'
]

export default function DailyDigestView({
  showToast,
  currentUser = null,
  killSwitchActive = false,
  setKillSwitchActive,
  setActiveTab
}) {
  const [subtab, setSubtab] = useState('digest') // 'digest' | 'history' | 'settings'

  // Run execution state
  const [isRunningManual, setIsRunningManual] = useState(false)
  const [latestDigest, setLatestDigest] = useState(null)
  const [loadingDigest, setLoadingDigest] = useState(true)

  // Run history state
  const [runs, setRuns] = useState([])
  const [loadingRuns, setLoadingRuns] = useState(false)
  const [expandedRunId, setExpandedRunId] = useState(null)
  const [runSteps, setRunSteps] = useState({})
  const [loadingSteps, setLoadingSteps] = useState({})

  // Schedule settings state
  const [settings, setSettings] = useState({
    daily_run_enabled: false,
    preferred_time: '08:00',
    timezone: 'UTC',
    permitted_sources: ['gmail', 'tasks', 'calendar'],
    kill_switch_enabled: false,
    next_run_at: null,
    last_run_at: null,
    last_run_status: 'never_run'
  })
  const [savingSettings, setSavingSettings] = useState(false)
  const [confirmEnableModal, setConfirmEnableModal] = useState(false)

  // Load latest digest and settings on mount
  const loadData = async () => {
    setLoadingDigest(true)
    try {
      const [digRes, setRes] = await Promise.all([
        fetchLatestDailyDigest(),
        fetchAgentSettings()
      ])
      if (digRes && digRes.digest) {
        setLatestDigest(digRes.digest)
      }
      if (setRes && setRes.settings) {
        setSettings(setRes.settings)
        if (setKillSwitchActive) {
          setKillSwitchActive(Boolean(setRes.settings.kill_switch_enabled))
        }
      }
    } catch {
      // Retain clean defaults
    } finally {
      setLoadingDigest(false)
    }
  }

  // Load run history when tab changes
  const loadRuns = async () => {
    setLoadingRuns(true)
    try {
      const res = await fetchAgentRuns()
      setRuns(res.runs || [])
    } catch {
      setRuns([])
    } finally {
      setLoadingRuns(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  useEffect(() => {
    if (subtab === 'history') {
      loadRuns()
    }
  }, [subtab])

  // Handle Manual "Run Now"
  const handleRunNow = async () => {
    if (killSwitchActive) {
      showToast('Run blocked: Emergency kill switch is currently engaged.')
      return
    }

    setIsRunningManual(true)
    showToast('Starting unattended daily agent run...')
    try {
      const res = await triggerManualAgentRun()
      if (res.success) {
        showToast(res.summary || 'Daily agent run completed successfully.')
        await loadData()
        if (subtab === 'history') await loadRuns()
      } else {
        showToast(`Run ended with status: ${res.status || 'failed'}`)
      }
    } catch (err) {
      showToast(err.message || 'Error executing agent run')
    } finally {
      setIsRunningManual(false)
    }
  }

  // Toggle Emergency Kill Switch
  const handleToggleKillSwitch = async () => {
    const nextVal = !killSwitchActive
    try {
      await setKillSwitchApi(nextVal)
      if (setKillSwitchActive) setKillSwitchActive(nextVal)
      setSettings(prev => ({ ...prev, kill_switch_enabled: nextVal }))
      showToast(nextVal ? 'Emergency Kill Switch Engaged. All unattended runs halted.' : 'Assistant engine resumed.')
    } catch {
      showToast('Failed to update kill switch state.')
    }
  }

  // Handle Settings Save
  const handleSaveSettings = async (newSettings) => {
    setSavingSettings(true)
    try {
      const res = await updateAgentSettings(newSettings)
      if (res.success && res.settings) {
        setSettings(res.settings)
        showToast('Schedule settings saved successfully.')
      }
    } catch (err) {
      showToast(err.message || 'Failed to save settings.')
    } finally {
      setSavingSettings(false)
    }
  }

  // Toggle Opt-in with explicit confirmation
  const handleToggleOptIn = (checked) => {
    if (checked && !settings.daily_run_enabled) {
      setConfirmEnableModal(true)
    } else {
      handleSaveSettings({ ...settings, daily_run_enabled: false })
    }
  }

  const confirmEnableSchedule = () => {
    setConfirmEnableModal(false)
    handleSaveSettings({ ...settings, daily_run_enabled: true })
  }

  // Toggle Source Checkbox
  const handleToggleSource = (sourceKey) => {
    const cur = settings.permitted_sources || []
    const updated = cur.includes(sourceKey)
      ? cur.filter(s => s !== sourceKey)
      : [...cur, sourceKey]
    setSettings(prev => ({ ...prev, permitted_sources: updated }))
  }

  // Expand Run Steps
  const toggleExpandRun = async (runId) => {
    if (expandedRunId === runId) {
      setExpandedRunId(null)
      return
    }
    setExpandedRunId(runId)
    if (!runSteps[runId]) {
      setLoadingSteps(prev => ({ ...prev, [runId]: true }))
      try {
        const res = await fetchAgentRunSteps(runId)
        setRunSteps(prev => ({ ...prev, [runId]: res.steps || [] }))
      } catch {
        setRunSteps(prev => ({ ...prev, [runId]: [] }))
      } finally {
        setLoadingSteps(prev => ({ ...prev, [runId]: false }))
      }
    }
  }

  const digestContent = latestDigest?.content || {}
  const emailsList = digestContent.important_emails || []
  const tasksObj = digestContent.tasks || {}
  const calObj = digestContent.calendar || {}
  const approvalsList = digestContent.pending_approvals || []
  const activityObj = digestContent.agent_activity || {}

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#DEDAD0] pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold tracking-tight text-[#242424]">Daily Briefing & Agent Runs</h1>
            <span className="rounded-full bg-[#D5E0BD] px-2.5 py-0.5 text-[11px] font-semibold text-[#171717]">
              Unattended Engine
            </span>
          </div>
          <p className="text-xs text-[#6B7280] mt-1">
            Supervised daily execution: reviews emails, audits tasks, detects schedule conflicts, and generates briefing summaries.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={handleRunNow}
            disabled={isRunningManual || killSwitchActive}
            className="flex items-center gap-2 rounded-xl bg-[#242424] px-4 py-2 text-xs font-semibold text-[#FFFDF8] hover:bg-[#383838] transition-colors disabled:opacity-40 cursor-pointer shadow-warm-sm"
          >
            {isRunningManual ? (
              <>
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                <span>Running Agent...</span>
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5" />
                <span>Run Agent Now</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Emergency Kill Switch Banner */}
      <div className={`rounded-2xl border p-4 shadow-warm-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 ${
        killSwitchActive ? 'border-[#EBC1D9] bg-[#FFFDF8]' : 'border-[#DEDAD0] bg-[#FFFDF8]'
      }`}>
        <div className="flex items-center gap-3">
          <div className={`rounded-xl p-2 ${killSwitchActive ? 'bg-[#EBC1D9] text-[#171717]' : 'bg-[#D5E0BD] text-[#171717]'}`}>
            <Power className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-[#242424]">
                {killSwitchActive ? 'Agent Engine: EMERGENCY STOPPED' : 'Supervisory Engine: Active & Auditing'}
              </span>
              <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
                killSwitchActive ? 'bg-[#EBC1D9] border-[#EBC1D9] text-[#171717]' : 'bg-[#D5E0BD]/60 border-[#D5E0BD] text-[#171717]'
              }`}>
                {killSwitchActive ? 'Halted' : 'Online'}
              </span>
            </div>
            <p className="text-[11px] text-[#6B7280] mt-0.5">
              {killSwitchActive
                ? 'All unattended runs, tool executions, and external operations are strictly blocked by the kill switch.'
                : 'Checked before runs and before every tool execution. Halts immediately if triggered.'}
            </p>
          </div>
        </div>

        <button
          onClick={handleToggleKillSwitch}
          className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-colors cursor-pointer shrink-0 ${
            killSwitchActive
              ? 'bg-[#242424] text-[#FFFDF8] hover:bg-[#383838]'
              : 'border border-[#EBC1D9] bg-[#EBC1D9]/30 text-[#171717] hover:bg-[#EBC1D9]/60'
          }`}
        >
          {killSwitchActive ? 'Resume Engine' : 'Engage Kill Switch'}
        </button>
      </div>

      {/* Navigation Subtab Switcher */}
      <div className="flex items-center gap-1.5 rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] p-1 text-xs shadow-warm-sm w-fit">
        <button
          onClick={() => setSubtab('digest')}
          className={`rounded-lg px-4 py-1.5 font-medium transition-colors cursor-pointer flex items-center gap-1.5 ${
            subtab === 'digest' ? 'bg-[#242424] text-[#FFFDF8]' : 'text-[#6B7280] hover:text-[#242424]'
          }`}
        >
          <Sparkles className="h-3.5 w-3.5" />
          <span>Latest Briefing</span>
        </button>

        <button
          onClick={() => setSubtab('history')}
          className={`rounded-lg px-4 py-1.5 font-medium transition-colors cursor-pointer flex items-center gap-1.5 ${
            subtab === 'history' ? 'bg-[#242424] text-[#FFFDF8]' : 'text-[#6B7280] hover:text-[#242424]'
          }`}
        >
          <History className="h-3.5 w-3.5" />
          <span>Run History & Traces</span>
        </button>

        <button
          onClick={() => setSubtab('settings')}
          className={`rounded-lg px-4 py-1.5 font-medium transition-colors cursor-pointer flex items-center gap-1.5 ${
            subtab === 'settings' ? 'bg-[#242424] text-[#FFFDF8]' : 'text-[#6B7280] hover:text-[#242424]'
          }`}
        >
          <Settings className="h-3.5 w-3.5" />
          <span>Schedule Settings</span>
        </button>
      </div>

      {/* ========================================================= */}
      {/* TAB 1: DAILY BRIEFING                                     */}
      {/* ========================================================= */}
      {subtab === 'digest' && (
        <div className="space-y-6">
          {loadingDigest ? (
            <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-16 text-center text-xs text-[#6B7280]">
              <RefreshCw className="mx-auto h-5 w-5 animate-spin mb-2 text-[#242424]" />
              Loading latest daily digest...
            </div>
          ) : !latestDigest ? (
            <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-12 text-center text-xs text-[#6B7280] space-y-3">
              <Sparkles className="mx-auto h-8 w-8 text-[#9CA3AF]" />
              <p className="font-semibold text-sm text-[#242424]">No Daily Briefing Generated Yet</p>
              <p className="max-w-md mx-auto text-[11px] leading-relaxed">
                The unattended daily agent has not run yet. Click "Run Agent Now" above to initiate a supervised audit of your inbox, tasks, and calendar.
              </p>
              <button
                onClick={handleRunNow}
                disabled={isRunningManual || killSwitchActive}
                className="mt-2 rounded-xl bg-[#242424] px-4 py-2 text-xs font-semibold text-[#FFFDF8] hover:bg-[#383838] transition-colors cursor-pointer"
              >
                Run First Daily Audit
              </button>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Digest Meta Bar */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] px-4 py-3 text-xs">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-[#242424]">{latestDigest.title}</span>
                  <span className="text-[#9CA3AF]">•</span>
                  <span className="font-mono text-[11px] text-[#6B7280]">{latestDigest.digest_date}</span>
                </div>
                <div className="flex items-center gap-2 text-[11px] font-mono text-[#6B7280]">
                  <span>Trigger: {digestContent.trigger_type || 'scheduled'}</span>
                  <span>•</span>
                  <span>Run ID: {latestDigest.run_id}</span>
                </div>
              </div>

              {/* 4-Column Core Section Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {/* 1. Important Emails */}
                <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm space-y-3 flex flex-col justify-between">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between border-b border-[#DEDAD0] pb-2 text-xs">
                      <div className="flex items-center gap-2 font-semibold text-[#242424]">
                        <Mail className="h-4 w-4 text-[#242424]" />
                        <span>Actionable Emails</span>
                      </div>
                      <span className="font-mono text-[11px] text-[#6B7280]">{emailsList.length} detected</span>
                    </div>

                    {emailsList.length === 0 ? (
                      <p className="text-xs text-[#6B7280] py-4">No urgent action items or deadlines detected in recent messages.</p>
                    ) : (
                      <div className="space-y-2.5">
                        {emailsList.map((em, idx) => (
                          <div key={idx} className="rounded-xl border border-[#DEDAD0] bg-[#F7F4EB]/60 p-3 text-xs space-y-1">
                            <div className="flex items-center justify-between">
                              <span className="font-semibold text-[#242424] truncate">{em.subject}</span>
                              <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                                em.urgency === 'high' ? 'bg-[#EBC1D9] border-[#EBC1D9] text-[#171717]' : 'bg-[#D5E0BD] border-[#D5E0BD] text-[#171717]'
                              }`}>
                                {em.urgency}
                              </span>
                            </div>
                            <p className="text-[11px] text-[#6B7280] line-clamp-2">{em.snippet}</p>
                            <div className="flex items-center justify-between pt-1 text-[10px] font-mono text-[#6B7280]">
                              <span>From: {em.sender}</span>
                              <span className="text-[#854D0E] font-medium">{em.recommended_action}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="pt-2 border-t border-[#DEDAD0] text-[11px] text-[#9CA3AF]">
                    Read-only Gmail integration active
                  </div>
                </div>

                {/* 2. Tasks Due Today & Overdue */}
                <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm space-y-3 flex flex-col justify-between">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between border-b border-[#DEDAD0] pb-2 text-xs">
                      <div className="flex items-center gap-2 font-semibold text-[#242424]">
                        <CheckSquare className="h-4 w-4 text-[#242424]" />
                        <span>Tasks Focus</span>
                      </div>
                      <span className="font-mono text-[11px] text-[#6B7280]">
                        {(tasksObj.due_today?.length || 0) + (tasksObj.overdue?.length || 0)} urgent
                      </span>
                    </div>

                    <div className="space-y-2">
                      {tasksObj.overdue && tasksObj.overdue.length > 0 && (
                        <div className="space-y-1">
                          <span className="text-[11px] font-semibold text-[#991B1B]">Overdue Tasks:</span>
                          {tasksObj.overdue.map((t, idx) => (
                            <div key={idx} className="flex items-center justify-between text-xs p-2 rounded-lg bg-[#EBC1D9]/20 border border-[#EBC1D9]">
                              <span className="font-medium text-[#242424] truncate">{t.title}</span>
                              <span className="text-[10px] font-mono text-[#991B1B]">{t.due_date}</span>
                            </div>
                          ))}
                        </div>
                      )}

                      {tasksObj.due_today && tasksObj.due_today.length > 0 ? (
                        <div className="space-y-1">
                          <span className="text-[11px] font-semibold text-[#854D0E]">Due Today:</span>
                          {tasksObj.due_today.map((t, idx) => (
                            <div key={idx} className="flex items-center justify-between text-xs p-2 rounded-lg bg-[#E9DB91]/20 border border-[#E9DB91]">
                              <span className="font-medium text-[#242424] truncate">{t.title}</span>
                              <span className="text-[10px] font-mono text-[#854D0E]">{t.priority}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-[#6B7280] py-2">No pending tasks due today.</p>
                      )}

                      {tasksObj.newly_created && tasksObj.newly_created.length > 0 && (
                        <div className="pt-2 border-t border-[#DEDAD0]">
                          <span className="text-[10px] font-semibold text-[#42542B] block mb-1">Created this run:</span>
                          <ul className="text-[11px] text-[#42542B] space-y-0.5">
                            {tasksObj.newly_created.map((nc, idx) => (
                              <li key={idx} className="truncate">• {nc}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="pt-2 border-t border-[#DEDAD0] text-[11px] text-[#9CA3AF]">
                    {tasksObj.completed_count || 0} completed tasks on record
                  </div>
                </div>

                {/* 3. Calendar & Conflicts */}
                <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm space-y-3 flex flex-col justify-between">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between border-b border-[#DEDAD0] pb-2 text-xs">
                      <div className="flex items-center gap-2 font-semibold text-[#242424]">
                        <Calendar className="h-4 w-4 text-[#242424]" />
                        <span>Calendar Schedule</span>
                      </div>
                      <span className="font-mono text-[11px] text-[#6B7280]">{calObj.today_events?.length || 0} today</span>
                    </div>

                    {calObj.conflicts && calObj.conflicts.length > 0 && (
                      <div className="rounded-xl border border-[#E9DB91] bg-[#E9DB91]/30 p-3 text-xs space-y-1">
                        <div className="flex items-center gap-1.5 font-semibold text-[#854D0E]">
                          <AlertTriangle className="h-3.5 w-3.5" />
                          <span>Detected Schedule Conflicts:</span>
                        </div>
                        {calObj.conflicts.map((c, idx) => (
                          <p key={idx} className="text-[11px] text-[#854D0E] font-mono leading-snug">{c}</p>
                        ))}
                      </div>
                    )}

                    {calObj.today_events && calObj.today_events.length > 0 ? (
                      <div className="space-y-1.5">
                        {calObj.today_events.map((e, idx) => (
                          <div key={idx} className="flex items-center justify-between text-xs p-2 rounded-lg bg-[#F7F4EB] border border-[#DEDAD0]">
                            <span className="font-medium text-[#242424] truncate">{e.title}</span>
                            <span className="text-[10px] font-mono text-[#6B7280]">{e.start_time} - {e.end_time}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-[#6B7280] py-4">No events scheduled on today's calendar.</p>
                    )}
                  </div>

                  <div className="pt-2 border-t border-[#DEDAD0] text-[11px] text-[#9CA3AF]">
                    {calObj.app_calendar_events || 0} application-calendar blocks stored
                  </div>
                </div>

                {/* 4. Pending Approvals & Safeguards */}
                <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm space-y-3 flex flex-col justify-between">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between border-b border-[#DEDAD0] pb-2 text-xs">
                      <div className="flex items-center gap-2 font-semibold text-[#242424]">
                        <ShieldAlert className="h-4 w-4 text-[#854D0E]" />
                        <span>Pending Approvals</span>
                      </div>
                      <span className="font-mono text-[11px] text-[#6B7280]">{approvalsList.length} queued</span>
                    </div>

                    {approvalsList.length === 0 ? (
                      <p className="text-xs text-[#6B7280] py-4">All proposed actions are either executed safely or clear. No risky actions pending approval.</p>
                    ) : (
                      <div className="space-y-2">
                        {approvalsList.map((appr, idx) => (
                          <div key={idx} className="rounded-xl border border-[#E9DB91] bg-[#E9DB91]/20 p-3 text-xs space-y-1">
                            <div className="flex items-center justify-between">
                              <span className="font-semibold text-[#242424] truncate">{appr.subject}</span>
                              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#E9DB91] text-[#854D0E] font-medium">
                                Review Required
                              </span>
                            </div>
                            <p className="text-[11px] text-[#6B7280]">{appr.reason}</p>
                            <span className="text-[10px] font-mono text-[#854D0E] block pt-1">To: {appr.target}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="pt-2 border-t border-[#DEDAD0] flex items-center justify-between">
                    <span className="text-[11px] text-[#9CA3AF]">Policy gate enforces human review</span>
                    {approvalsList.length > 0 && (
                      <button
                        onClick={() => setActiveTab('approvals')}
                        className="text-xs font-semibold text-[#242424] hover:underline flex items-center gap-1 cursor-pointer"
                      >
                        <span>Review Queue</span>
                        <ArrowRight className="h-3 w-3" />
                      </button>
                    )}
                  </div>
                </div>
              </div>

              {/* Attention Summary Card */}
              {activityObj.attention_items && activityObj.attention_items.length > 0 && (
                <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm space-y-3">
                  <div className="flex items-center gap-2 text-xs font-semibold text-[#242424]">
                    <Sparkles className="h-4 w-4 text-[#242424]" />
                    <span>Agent Summary & Attention Items</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                    {activityObj.attention_items.map((it, idx) => (
                      <div key={idx} className="rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-3 text-center">
                        <span className="font-medium text-[#242424]">{it}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ========================================================= */}
      {/* TAB 2: RUN HISTORY & EXECUTION TRACES                    */}
      {/* ========================================================= */}
      {subtab === 'history' && (
        <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm space-y-4">
          <div className="flex items-center justify-between border-b border-[#DEDAD0] pb-3 text-xs">
            <div className="flex items-center gap-2 font-semibold text-[#242424]">
              <History className="h-4 w-4 text-[#242424]" />
              <span>Unattended Execution History</span>
            </div>
            <button
              onClick={loadRuns}
              className="text-[#6B7280] hover:text-[#242424] flex items-center gap-1 font-mono text-[11px] cursor-pointer"
            >
              <RefreshCw className="h-3 w-3" />
              <span>Refresh</span>
            </button>
          </div>

          {loadingRuns ? (
            <div className="py-16 text-center text-xs text-[#6B7280]">
              <RefreshCw className="mx-auto h-5 w-5 animate-spin mb-1 text-[#242424]" />
              Loading run audit log...
            </div>
          ) : runs.length === 0 ? (
            <div className="py-16 text-center text-xs text-[#6B7280]">
              No unattended agent runs recorded yet.
            </div>
          ) : (
            <div className="divide-y divide-[#DEDAD0]">
              {runs.map((r) => {
                const isExpanded = expandedRunId === r.id
                const steps = runSteps[r.id] || []
                const isStepsLoading = loadingSteps[r.id]

                return (
                  <div key={r.id} className="py-3.5 first:pt-0 last:pb-0 space-y-3">
                    <div
                      onClick={() => toggleExpandRun(r.id)}
                      className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 cursor-pointer hover:bg-[#F7F4EB]/50 p-2 -mx-2 rounded-xl transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <span className={`flex h-2.5 w-2.5 rounded-full shrink-0 ${
                          r.status === 'completed'
                            ? 'bg-[#708A4E]'
                            : r.status === 'stopped_by_kill_switch' || r.status === 'failed'
                            ? 'bg-[#B91C1C]'
                            : 'bg-[#D97706]'
                        }`} />
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-xs text-[#242424]">{r.id}</span>
                            <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
                              r.status === 'completed'
                                ? 'bg-[#D5E0BD] border-[#D5E0BD] text-[#171717]'
                                : r.status === 'stopped_by_kill_switch'
                                ? 'bg-[#EBC1D9] border-[#EBC1D9] text-[#171717]'
                                : 'bg-[#E9DB91] border-[#E9DB91] text-[#171717]'
                            }`}>
                              {r.status}
                            </span>
                            <span className="text-[11px] font-mono text-[#6B7280]">({r.trigger_type})</span>
                          </div>
                          <p className="text-[11px] text-[#6B7280] mt-0.5">{r.summary || 'Unattended execution'}</p>
                        </div>
                      </div>

                      <div className="flex items-center gap-3 text-right">
                        <div className="text-[11px] font-mono text-[#6B7280]">
                          <div>{r.started_at ? new Date(r.started_at).toLocaleTimeString() : 'N/A'}</div>
                          <div className="text-[10px] text-[#9CA3AF]">{r.total_steps} steps audited</div>
                        </div>
                        {isExpanded ? <ChevronDown className="h-4 w-4 text-[#6B7280]" /> : <ChevronRight className="h-4 w-4 text-[#6B7280]" />}
                      </div>
                    </div>

                    {/* Expanded Steps Audit */}
                    {isExpanded && (
                      <div className="rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-4 space-y-2 text-xs">
                        <div className="flex items-center justify-between border-b border-[#DEDAD0] pb-1.5 font-semibold text-[#242424]">
                          <span>Step-by-Step Execution Trace</span>
                          <span className="font-mono text-[10px] text-[#6B7280]">{steps.length} Steps</span>
                        </div>

                        {isStepsLoading ? (
                          <div className="py-4 text-center text-xs text-[#6B7280]">Loading audit steps...</div>
                        ) : steps.length === 0 ? (
                          <div className="py-4 text-center text-xs text-[#6B7280]">No step records available for this run.</div>
                        ) : (
                          <div className="space-y-2 pt-1">
                            {steps.map((st) => (
                              <div key={st.id} className="rounded-lg border border-[#DEDAD0] bg-[#FFFDF8] p-2.5 text-xs space-y-1">
                                <div className="flex items-center justify-between">
                                  <span className="font-medium text-[#242424]">
                                    Step {st.step_number}: {st.step_name}
                                  </span>
                                  <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                                    st.status === 'completed'
                                      ? 'bg-[#D5E0BD]/50 border-[#D5E0BD] text-[#42542B]'
                                      : 'bg-[#EBC1D9]/50 border-[#EBC1D9] text-[#991B1B]'
                                  }`}>
                                    {st.policy_decision}
                                  </span>
                                </div>
                                <p className="text-[11px] text-[#6B7280]">{st.result}</p>
                                {st.tool_name && (
                                  <div className="text-[10px] font-mono text-[#9CA3AF] pt-0.5">
                                    Tool: {st.tool_name} • Latency: {st.latency_ms || '0ms'}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* ========================================================= */}
      {/* TAB 3: SCHEDULE SETTINGS                                  */}
      {/* ========================================================= */}
      {subtab === 'settings' && (
        <div className="space-y-6">
          <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-6 shadow-warm-sm space-y-6 max-w-2xl">
            <div className="border-b border-[#DEDAD0] pb-3">
              <h2 className="text-sm font-semibold text-[#242424]">Unattended Execution Configuration</h2>
              <p className="text-xs text-[#6B7280] mt-0.5">
                Configure when and how your personal assistant independently reviews work. Scheduled execution is strictly opt-in.
              </p>
            </div>

            {/* Opt-in Switch */}
            <div className="flex items-start justify-between gap-4 p-4 rounded-xl border border-[#DEDAD0] bg-[#F7F4EB]">
              <div className="space-y-0.5">
                <label className="text-xs font-semibold text-[#242424]">Enable Daily Unattended Run</label>
                <p className="text-[11px] text-[#6B7280] leading-relaxed">
                  When enabled, the assistant will automatically execute permitted actions at your preferred time.
                </p>
              </div>

              <input
                type="checkbox"
                checked={settings.daily_run_enabled}
                onChange={(e) => handleToggleOptIn(e.target.checked)}
                className="h-4 w-4 rounded border-[#DEDAD0] text-[#242424] focus:ring-0 cursor-pointer mt-0.5"
              />
            </div>

            {/* Time & Timezone */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-[#242424]">Execution Time</label>
                <input
                  type="time"
                  value={settings.preferred_time}
                  onChange={(e) => setSettings(prev => ({ ...prev, preferred_time: e.target.value }))}
                  className="w-full rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
                />
                <span className="text-[10px] text-[#9CA3AF]">Runs daily at this minute</span>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-[#242424]">Timezone</label>
                <select
                  value={settings.timezone}
                  onChange={(e) => setSettings(prev => ({ ...prev, timezone: e.target.value }))}
                  className="w-full rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
                >
                  {COMMON_TIMEZONES.map(tz => (
                    <option key={tz} value={tz}>{tz}</option>
                  ))}
                </select>
                <span className="text-[10px] text-[#9CA3AF]">User-configured local time</span>
              </div>
            </div>

            {/* Permitted Data Sources */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-[#242424]">Permitted Data Sources</label>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {[
                  { key: 'gmail', label: 'Gmail (Read-Only)', desc: 'Extract deadlines' },
                  { key: 'tasks', label: 'Tasks Store', desc: 'Audit due items' },
                  { key: 'calendar', label: 'Calendar Store', desc: 'Inspect clashes' }
                ].map((s) => {
                  const isChecked = (settings.permitted_sources || []).includes(s.key)
                  return (
                    <div
                      key={s.key}
                      onClick={() => handleToggleSource(s.key)}
                      className={`p-3 rounded-xl border text-xs cursor-pointer transition-all ${
                        isChecked
                          ? 'border-[#242424] bg-[#F7F4EB] text-[#242424] font-medium'
                          : 'border-[#DEDAD0] bg-[#FFFDF8] text-[#6B7280]'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span>{s.label}</span>
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => {}}
                          className="h-3.5 w-3.5 text-[#242424] rounded"
                        />
                      </div>
                      <p className="text-[10px] text-[#9CA3AF] mt-1">{s.desc}</p>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Schedule Status Indicators */}
            <div className="rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-4 text-xs space-y-2 font-mono">
              <div className="flex items-center justify-between text-[#6B7280]">
                <span>Next Scheduled Run:</span>
                <span className="text-[#242424] font-medium">{settings.next_run_at ? new Date(settings.next_run_at).toLocaleString() : 'Not scheduled (opt-in disabled)'}</span>
              </div>
              <div className="flex items-center justify-between text-[#6B7280]">
                <span>Last Run Status:</span>
                <span className="text-[#242424] font-medium">{settings.last_run_status || 'Never run'}</span>
              </div>
            </div>

            <button
              onClick={() => handleSaveSettings(settings)}
              disabled={savingSettings}
              className="rounded-xl bg-[#242424] px-5 py-2 text-xs font-semibold text-[#FFFDF8] hover:bg-[#383838] transition-colors disabled:opacity-40 cursor-pointer shadow-warm-sm"
            >
              {savingSettings ? 'Saving...' : 'Save Settings'}
            </button>
          </div>

          {/* Safety Bounds Card */}
          <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-6 shadow-warm-sm space-y-3 max-w-2xl">
            <div className="flex items-center gap-2 text-xs font-semibold text-[#242424]">
              <Lock className="h-4 w-4 text-[#708A4E]" />
              <span>What the Unattended Agent Can and Cannot Do</span>
            </div>
            <ul className="text-xs text-[#6B7280] space-y-1.5 leading-relaxed">
              <li className="flex items-start gap-2">
                <CheckCircle2 className="h-3.5 w-3.5 text-[#708A4E] shrink-0 mt-0.5" />
                <span><strong>Permitted:</strong> Scans read-only inbox for deadlines, audits pending tasks, creates internal tasks, detects calendar clashes.</span>
              </li>
              <li className="flex items-start gap-2">
                <XCircle className="h-3.5 w-3.5 text-[#B91C1C] shrink-0 mt-0.5" />
                <span><strong>Strictly Prohibited:</strong> Direct email sending, monetary transactions, form submissions, or external deletions.</span>
              </li>
              <li className="flex items-start gap-2">
                <ShieldAlert className="h-3.5 w-3.5 text-[#854D0E] shrink-0 mt-0.5" />
                <span><strong>Approval Queue:</strong> Outbound replies are formulated as drafts and placed in your Approvals inbox for explicit human review.</span>
              </li>
            </ul>
          </div>
        </div>
      )}

      {/* Confirmation Modal for Enabling Opt-in */}
      {confirmEnableModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="w-full max-w-md rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-6 shadow-warm-lg space-y-4">
            <div className="flex items-center gap-2.5">
              <div className="rounded-xl bg-[#D5E0BD] p-2 text-[#171717]">
                <Sparkles className="h-4 w-4" />
              </div>
              <h3 className="text-sm font-semibold text-[#242424]">Confirm Unattended Execution</h3>
            </div>

            <p className="text-xs text-[#6B7280] leading-relaxed">
              Enabling scheduled execution permits the assistant to run in the background at your preferred time daily.
              The agent operates under strict supervision: it reads authorized data, prepares internal tasks, and stops immediately if the emergency kill switch is activated.
            </p>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-[#DEDAD0]">
              <button
                onClick={() => setConfirmEnableModal(false)}
                className="rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] px-3.5 py-1.5 text-xs font-medium text-[#6B7280] hover:text-[#242424] cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={confirmEnableSchedule}
                className="rounded-xl bg-[#242424] px-4 py-1.5 text-xs font-semibold text-[#FFFDF8] hover:bg-[#383838] transition-colors cursor-pointer shadow-warm-sm"
              >
                Enable Scheduled Runs
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
