import React, { useState, useEffect } from 'react'
import {
  Mail,
  Lock,
  RefreshCw,
  ChevronRight,
  ChevronLeft,
  AlertTriangle,
  Plus,
  Search,
  ShieldCheck,
  Clock
} from 'lucide-react'
import {
  fetchGmailMessages,
  fetchGmailMessageDetail,
  disconnectGmail,
  createUserTask,
  getGoogleAuthUrl
} from '../api'

export default function InboxView({
  currentUser,
  gmailConnected,
  onGmailStatusChange,
  showToast,
  onTaskCreated
}) {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedMessageId, setSelectedMessageId] = useState(null)
  const [selectedMessageDetail, setSelectedMessageDetail] = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [nextPageToken, setNextPageToken] = useState(null)
  const [pageHistory, setPageHistory] = useState([])
  const [currentPageToken, setCurrentPageToken] = useState(null)
  const [disconnecting, setDisconnecting] = useState(false)

  // Filter & Search Controls
  const [searchQuery, setSearchQuery] = useState('')
  const [filterMode, setFilterMode] = useState('all') // 'all' | 'unread'

  const loadMessages = async (token = null) => {
    if (!gmailConnected) {
      setMessages([])
      return
    }

    setLoading(true)
    setError(null)
    try {
      const data = await fetchGmailMessages(token, 15)
      if (data.connected === false) {
        if (data.error) setError(data.error)
        onGmailStatusChange(false)
        setMessages([])
      } else {
        const msgs = data.messages || []
        setMessages(msgs)
        setNextPageToken(data.nextPageToken || null)
        setCurrentPageToken(token)

        if (msgs.length > 0 && !selectedMessageId) {
          loadMessageDetail(msgs[0].id)
        }
      }
    } catch (err) {
      setError(err.message || 'Failed to load inbox messages from Gmail.')
      setMessages([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadMessages(null)
  }, [gmailConnected])

  const loadMessageDetail = async (id) => {
    setSelectedMessageId(id)
    setLoadingDetail(true)
    try {
      const detail = await fetchGmailMessageDetail(id)
      setSelectedMessageDetail(detail)
    } catch {
      showToast('Could not load full message content.')
    } finally {
      setLoadingDetail(false)
    }
  }

  const handleNextPage = () => {
    if (!nextPageToken) return
    setPageHistory(prev => [...prev, currentPageToken])
    loadMessages(nextPageToken)
  }

  const handlePrevPage = () => {
    if (pageHistory.length === 0) return
    const prevToken = pageHistory[pageHistory.length - 1]
    setPageHistory(prev => prev.slice(0, prev.length - 1))
    loadMessages(prevToken)
  }

  const handleDisconnect = async () => {
    if (!window.confirm('Are you sure you want to disconnect Gmail?')) return
    setDisconnecting(true)
    try {
      await disconnectGmail()
      onGmailStatusChange(false)
      setMessages([])
      setSelectedMessageDetail(null)
      setSelectedMessageId(null)
      showToast('Gmail account disconnected.')
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

  const handleExtractTask = async () => {
    if (!selectedMessageDetail) return
    try {
      await createUserTask({
        title: `Follow up: ${selectedMessageDetail.subject || 'Email Action'}`,
        source: `Email: ${selectedMessageDetail.senderName || selectedMessageDetail.from}`,
        source_email_id: selectedMessageDetail.id,
        due_date: 'Inbox review',
        priority: 'normal',
        workspace: 'General'
      })
      showToast('Task created and linked to this email.')
      if (onTaskCreated) onTaskCreated()
    } catch {
      showToast('Failed to create task.')
    }
  }

  // Filter messages locally by unread state and search query
  const filteredMessages = messages.filter((m) => {
    if (filterMode === 'unread' && !m.isUnread) return false
    if (!searchQuery.trim()) return true
    const q = searchQuery.toLowerCase()
    return (
      (m.subject && m.subject.toLowerCase().includes(q)) ||
      (m.senderName && m.senderName.toLowerCase().includes(q)) ||
      (m.snippet && m.snippet.toLowerCase().includes(q)) ||
      (m.from && m.from.toLowerCase().includes(q))
    )
  })

  // Disconnected state
  if (!gmailConnected) {
    return (
      <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-8 sm:p-12 text-center space-y-4 shadow-warm-sm">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-[#F7F4EB] border border-[#DEDAD0]">
          <Mail className="h-6 w-6 text-[#242424]" />
        </div>
        <div className="space-y-1">
          <h2 className="text-base font-semibold text-[#242424]">Gmail Account Not Connected</h2>
          <p className="text-xs text-[#6B7280] max-w-md mx-auto">
            Connect your Google account with read-only permissions to inspect incoming messages, extract tasks, and track scheduling in your assistant.
          </p>
        </div>

        <div className="pt-2">
          <button
            onClick={handleConnectGmail}
            className="inline-flex items-center gap-2 rounded-xl bg-[#242424] px-5 py-2.5 text-xs font-semibold text-[#FFFDF8] hover:bg-[#383838] transition-colors cursor-pointer"
          >
            <Mail className="h-4 w-4" />
            <span>Connect Read-Only Gmail</span>
          </button>
        </div>

        <div className="pt-4 border-t border-[#DEDAD0] text-[11px] text-[#6B7280] flex items-center justify-center gap-2">
          <Lock className="h-3.5 w-3.5 text-[#6B7280]" />
          <span>Strictly Read-Only: No email sending, deleting, or modification access.</span>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Top Banner: Status & Governance */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] px-5 py-3 shadow-warm-sm">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#D5E0BD]/50 border border-[#D5E0BD] text-[#242424]">
            <ShieldCheck className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-[#242424]">
                Gmail Integration Active (Read-Only)
              </span>
              <span className="rounded bg-[#D5E0BD]/60 px-2 py-0.5 text-[10px] font-mono font-medium text-[#171717]">
                gmail.readonly
              </span>
            </div>
            <div className="text-[11px] text-[#6B7280]">
              Account: <span className="font-mono text-[#242424]">{currentUser?.email}</span> • Direct email sending is disabled
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => loadMessages(currentPageToken)}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-[#DEDAD0] bg-[#F7F4EB] px-3 py-1.5 text-xs font-medium text-[#242424] hover:bg-[#EFECE2] transition-colors cursor-pointer"
          >
            <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>

          <button
            onClick={handleDisconnect}
            disabled={disconnecting}
            className="rounded-lg border border-[#DEDAD0] bg-[#FFFDF8] px-3 py-1.5 text-xs font-medium text-[#6B7280] hover:text-[#B91C1C] hover:border-[#EBC1D9] transition-colors cursor-pointer"
          >
            {disconnecting ? 'Disconnecting...' : 'Disconnect'}
          </button>
        </div>
      </div>

      {/* Main Split-Panel Workspace: Left = Email List, Right = Email Reading Pane */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12 min-h-[620px]">
        {/* Left Column: Messages List (5 of 12 columns) */}
        <div className="lg:col-span-5 rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] flex flex-col shadow-warm-sm overflow-hidden">
          {/* Search & Filter Header */}
          <div className="p-3.5 border-b border-[#DEDAD0] space-y-2.5 bg-[#FFFDF8]">
            {/* Search Input */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[#9CA3AF]" />
              <input
                type="text"
                placeholder="Search sender, subject..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full rounded-lg border border-[#DEDAD0] bg-[#F7F4EB] py-1.5 pl-9 pr-3 text-xs text-[#242424] placeholder:text-[#9CA3AF] focus:border-[#242424] focus:bg-[#FFFDF8] focus:outline-none transition-all"
              />
            </div>

            {/* Filter Tabs */}
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setFilterMode('all')}
                  className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                    filterMode === 'all'
                      ? 'bg-[#242424] text-[#FFFDF8]'
                      : 'text-[#6B7280] hover:bg-[#F7F4EB]'
                  }`}
                >
                  All ({messages.length})
                </button>
                <button
                  onClick={() => setFilterMode('unread')}
                  className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                    filterMode === 'unread'
                      ? 'bg-[#242424] text-[#FFFDF8]'
                      : 'text-[#6B7280] hover:bg-[#F7F4EB]'
                  }`}
                >
                  Unread ({messages.filter(m => m.isUnread).length})
                </button>
              </div>

              <span className="text-[11px] text-[#9CA3AF] font-mono">
                {filteredMessages.length} shown
              </span>
            </div>
          </div>

          {/* Messages Scroll List */}
          <div className="flex-1 overflow-y-auto divide-y divide-[#DEDAD0]">
            {loading ? (
              <div className="py-16 text-center text-xs text-[#6B7280] space-y-2">
                <RefreshCw className="mx-auto h-5 w-5 animate-spin text-[#242424]" />
                <p>Fetching messages from Gmail...</p>
              </div>
            ) : error ? (
              <div className="p-6 text-center text-xs text-[#B91C1C] space-y-2">
                <AlertTriangle className="mx-auto h-5 w-5 text-[#B91C1C]" />
                <p>{error}</p>
                <button
                  onClick={() => loadMessages(null)}
                  className="mt-1 rounded-lg border border-[#DEDAD0] bg-[#F7F4EB] px-3 py-1 text-xs text-[#242424]"
                >
                  Retry
                </button>
              </div>
            ) : filteredMessages.length === 0 ? (
              <div className="py-16 text-center text-xs text-[#6B7280]">
                No messages match the current filter.
              </div>
            ) : (
              filteredMessages.map((msg) => {
                const isSelected = selectedMessageId === msg.id
                return (
                  <div
                    key={msg.id}
                    onClick={() => loadMessageDetail(msg.id)}
                    className={`p-3.5 transition-colors cursor-pointer border-l-2 ${
                      isSelected
                        ? 'bg-[#F7F4EB] border-l-[#242424]'
                        : 'border-l-transparent hover:bg-[#F7F4EB]/50'
                    }`}
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        {msg.isUnread && (
                          <span className="h-2 w-2 rounded-full bg-[#3B82F6] shrink-0" />
                        )}
                        <span
                          className={`text-xs truncate ${
                            msg.isUnread ? 'font-semibold text-[#242424]' : 'text-[#4B5563]'
                          }`}
                        >
                          {msg.senderName || msg.from}
                        </span>
                      </div>
                      <span className="text-[10px] text-[#9CA3AF] font-mono shrink-0">
                        {msg.date ? msg.date.split(' ').slice(0, 3).join(' ') : ''}
                      </span>
                    </div>

                    <div
                      className={`text-xs truncate mt-1 ${
                        msg.isUnread ? 'font-semibold text-[#242424]' : 'font-medium text-[#374151]'
                      }`}
                    >
                      {msg.subject || '(No subject)'}
                    </div>

                    <p className="text-[11px] text-[#6B7280] line-clamp-2 mt-1 leading-snug">
                      {msg.snippet}
                    </p>

                    {/* Urgency & Label Badges */}
                    <div className="flex items-center gap-1.5 mt-2">
                      {msg.isUnread && (
                        <span className="rounded bg-[#B9CDE7]/50 border border-[#B9CDE7] px-1.5 py-0.2 text-[9px] font-semibold text-[#171717]">
                          Unread
                        </span>
                      )}
                      {msg.labels && msg.labels.includes('IMPORTANT') && (
                        <span className="rounded bg-[#E9DB91]/50 border border-[#E9DB91] px-1.5 py-0.2 text-[9px] font-semibold text-[#171717]">
                          Important
                        </span>
                      )}
                    </div>
                  </div>
                )
              })
            )}
          </div>

          {/* Pagination Controls */}
          <div className="p-3 border-t border-[#DEDAD0] bg-[#FFFDF8] flex items-center justify-between text-xs">
            <button
              onClick={handlePrevPage}
              disabled={pageHistory.length === 0 || loading}
              className="flex items-center gap-1 rounded-lg border border-[#DEDAD0] bg-[#F7F4EB] px-2.5 py-1 text-xs text-[#242424] hover:bg-[#EFECE2] disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              <span>Previous</span>
            </button>

            <span className="text-[11px] text-[#6B7280]">
              Page {pageHistory.length + 1}
            </span>

            <button
              onClick={handleNextPage}
              disabled={!nextPageToken || loading}
              className="flex items-center gap-1 rounded-lg border border-[#DEDAD0] bg-[#F7F4EB] px-2.5 py-1 text-xs text-[#242424] hover:bg-[#EFECE2] disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
            >
              <span>Next</span>
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* Right Column: Selected Message Reading Workspace (7 of 12 columns) */}
        <div className="lg:col-span-7 rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] flex flex-col shadow-warm-sm overflow-hidden">
          {loadingDetail ? (
            <div className="flex-1 flex flex-col items-center justify-center p-12 text-xs text-[#6B7280] space-y-2">
              <RefreshCw className="h-5 w-5 animate-spin text-[#242424]" />
              <p>Loading email detail...</p>
            </div>
          ) : !selectedMessageDetail ? (
            <div className="flex-1 flex flex-col items-center justify-center p-12 text-xs text-[#6B7280] space-y-2">
              <Mail className="h-8 w-8 text-[#D1D5DB]" />
              <p>Select an email from the left pane to read its content.</p>
            </div>
          ) : (
            <div className="flex-1 flex flex-col h-full">
              {/* Header Bar */}
              <div className="p-5 border-b border-[#DEDAD0] space-y-3 bg-[#FFFDF8]">
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="text-base font-semibold text-[#242424] break-words">
                      {selectedMessageDetail.subject || '(No subject)'}
                    </h2>
                    <div className="flex items-center gap-2 mt-1 text-xs text-[#6B7280]">
                      <span className="font-semibold text-[#242424]">
                        {selectedMessageDetail.senderName || selectedMessageDetail.from}
                      </span>
                      <span>•</span>
                      <span className="font-mono text-[11px] text-[#6B7280]">
                        {selectedMessageDetail.from}
                      </span>
                    </div>
                  </div>

                  {/* Extract Task Action Button */}
                  <button
                    onClick={handleExtractTask}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-[#DEDAD0] bg-[#F7F4EB] px-3 py-1.5 text-xs font-semibold text-[#242424] hover:bg-[#EFECE2] hover:border-[#242424] transition-all shrink-0 cursor-pointer shadow-warm-sm"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    <span>Extract Task</span>
                  </button>
                </div>

                {/* Metadata & Date */}
                <div className="flex items-center justify-between text-[11px] text-[#6B7280] pt-1">
                  <div className="flex items-center gap-2 font-mono">
                    <Clock className="h-3 w-3 text-[#9CA3AF]" />
                    <span>{selectedMessageDetail.date}</span>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <span className="rounded bg-[#F7F4EB] border border-[#DEDAD0] px-2 py-0.5 text-[10px] font-mono text-[#6B7280]">
                      ID: {selectedMessageDetail.id.substring(0, 10)}...
                    </span>
                  </div>
                </div>
              </div>

              {/* Message Body Content (Untrusted Boundary - Sanitized preview) */}
              <div className="flex-1 overflow-y-auto p-6 bg-[#FFFDF8]">
                <div className="max-w-2xl text-xs text-[#242424] leading-relaxed whitespace-pre-wrap font-sans selection:bg-[#B9CDE7]">
                  {selectedMessageDetail.body || selectedMessageDetail.snippet || '(No message body available)'}
                </div>
              </div>

              {/* Security Boundary Guardrail Footer */}
              <div className="p-3 border-t border-[#DEDAD0] bg-[#F7F4EB] flex items-center justify-between text-[11px] text-[#6B7280]">
                <div className="flex items-center gap-1.5">
                  <Lock className="h-3.5 w-3.5 text-[#6B7280]" />
                  <span>External Email Content Boundary • Untrusted text rendered securely</span>
                </div>
                <span className="font-mono text-[10px] text-[#9CA3AF]">Supervised Read-Only</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
