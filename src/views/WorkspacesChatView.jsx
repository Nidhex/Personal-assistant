import React, { useState, useEffect, useRef } from 'react'
import {
  Lock,
  Plus,
  Send,
  Bot,
  User,
  FolderOpen,
  ChevronRight,
  MessageSquare,
  Trash2,
  RefreshCw,
  Sparkles,
  ShieldAlert,
  AlertTriangle,
  FileText,
  CheckCircle2,
  Calendar,
  Clock,
  Layers,
  StickyNote
} from 'lucide-react'
import {
  createUserWorkspace,
  fetchConversations,
  createConversation,
  fetchConversationMessages,
  sendChatMessage,
  deleteConversation,
  fetchWorkspaceNotes,
  createWorkspaceNote
} from '../api'

// Simple helper to render basic markdown elements (headers, bold, lists, code blocks)
function formatMessageContent(content, isAssistant = true) {
  if (!content) return ''
  const headingText = isAssistant ? 'text-[#242424]' : 'text-[#FFFDF8]'
  const bodyText = isAssistant ? 'text-[#374151]' : 'text-[#FFFDF8]'
  const lines = content.split('\n')
  const formatted = []
  let inCodeBlock = false
  let codeBuffer = []

  lines.forEach((line, idx) => {
    if (line.startsWith('```')) {
      if (inCodeBlock) {
        formatted.push(
          <pre
            key={`code-${idx}`}
            className="my-2 p-3 rounded-xl bg-[#171717] text-[#EDEDED] font-mono text-[11px] overflow-x-auto leading-relaxed border border-[#2E2E2E]"
          >
            {codeBuffer.join('\n')}
          </pre>
        )
        codeBuffer = []
        inCodeBlock = false
      } else {
        inCodeBlock = true
      }
      return
    }

    if (inCodeBlock) {
      codeBuffer.push(line)
      return
    }

    if (line.startsWith('### ')) {
      formatted.push(
        <h4 key={idx} className={`font-semibold text-xs ${headingText} mt-2 mb-1`}>
          {line.replace('### ', '')}
        </h4>
      )
    } else if (line.startsWith('## ')) {
      formatted.push(
        <h3 key={idx} className={`font-semibold text-sm ${headingText} mt-2 mb-1`}>
          {line.replace('## ', '')}
        </h3>
      )
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      formatted.push(
        <li key={idx} className={`ml-4 list-disc text-xs ${bodyText} my-0.5 leading-relaxed`}>
          {line.substring(2)}
        </li>
      )
    } else if (line.trim()) {
      formatted.push(
        <p key={idx} className="text-xs text-[#374151] my-1 leading-relaxed">
          {line}
        </p>
      )
    } else {
      formatted.push(<div key={idx} className="h-1.5" />)
    }
  })

  return formatted
}

export default function WorkspacesChatView({
  workspaces = [],
  onWorkspacesChanged,
  activeWorkspaceId,
  setActiveWorkspaceId,
  isMainChatOnly = false,
  killSwitchActive,
  showToast
}) {
  const [activeWsId, setActiveWsId] = useState(
    activeWorkspaceId || (workspaces[0] ? workspaces[0].id : 'main')
  )

  // Conversations & Messages State
  const [conversations, setConversations] = useState([])
  const [activeConvId, setActiveConvId] = useState(null)
  const [messages, setMessages] = useState([])
  const [loadingConversations, setLoadingConversations] = useState(false)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [sending, setSending] = useState(false)
  const [chatInput, setChatInput] = useState('')

  // Workspace Creation Modal State
  const [isCreatingWs, setIsCreatingWs] = useState(false)
  const [newWsName, setNewWsName] = useState('')
  const [newWsType, setNewWsType] = useState('Project')
  const [newWsDesc, setNewWsDesc] = useState('')
  const [creatingWs, setCreatingWs] = useState(false)

  // Workspace Notes State
  const [workspaceNotes, setWorkspaceNotes] = useState([])
  const [isAddingNote, setIsAddingNote] = useState(false)
  const [noteTitle, setNoteTitle] = useState('')
  const [noteContent, setNoteContent] = useState('')
  const [savingNote, setSavingNote] = useState(false)

  const messagesEndRef = useRef(null)

  const currentWs = !isMainChatOnly
    ? workspaces.find(w => w.id === (activeWorkspaceId || activeWsId)) || workspaces[0] || null
    : null

  const effectiveWorkspaceId = isMainChatOnly ? 'main' : (currentWs ? currentWs.id : 'main')

  // Auto-scroll to bottom of chat
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, sending])

  // Load conversations when workspace changes
  const loadConversations = async () => {
    setLoadingConversations(true)
    try {
      const data = await fetchConversations(effectiveWorkspaceId)
      const convs = data.conversations || []
      setConversations(convs)

      if (convs.length > 0) {
        // Select first conversation
        setActiveConvId(convs[0].id)
        loadMessages(convs[0].id)
      } else {
        // Create initial conversation automatically
        await handleNewConversation()
      }
    } catch {
      showToast('Could not load conversation history.')
    } finally {
      setLoadingConversations(false)
    }
  }

  // Load messages for selected conversation
  const loadMessages = async (convId) => {
    if (!convId) return
    setActiveConvId(convId)
    setLoadingMessages(true)
    try {
      const data = await fetchConversationMessages(convId)
      setMessages(data.messages || [])
    } catch {
      showToast('Failed to load messages.')
    } finally {
      setLoadingMessages(false)
    }
  }

  // Load workspace notes if in workspace mode
  const loadWorkspaceNotes = async (wsId) => {
    if (!wsId || wsId === 'main') {
      setWorkspaceNotes([])
      return
    }
    try {
      const data = await fetchWorkspaceNotes(wsId)
      setWorkspaceNotes(data.notes || [])
    } catch {
      setWorkspaceNotes([])
    }
  }

  useEffect(() => {
    loadConversations()
    if (!isMainChatOnly && currentWs) {
      loadWorkspaceNotes(currentWs.id)
    }
  }, [effectiveWorkspaceId, isMainChatOnly])

  // Create new conversation
  const handleNewConversation = async () => {
    try {
      const title = isMainChatOnly ? 'General Assistant Chat' : `${currentWs?.name || 'Workspace'} Chat`
      const data = await createConversation(effectiveWorkspaceId, title)
      if (data.conversation) {
        setConversations(prev => [data.conversation, ...prev])
        setActiveConvId(data.conversation.id)
        setMessages([])
      }
    } catch {
      showToast('Failed to initialize new conversation.')
    }
  }

  // Delete conversation
  const handleDeleteConversation = async (convId, e) => {
    e.stopPropagation()
    if (!window.confirm('Delete this conversation history?')) return
    try {
      await deleteConversation(convId)
      setConversations(prev => prev.filter(c => c.id !== convId))
      showToast('Conversation deleted.')
      if (activeConvId === convId) {
        loadConversations()
      }
    } catch {
      showToast('Failed to delete conversation.')
    }
  }

  // Send message
  const handleSendMessage = async (e) => {
    if (e) e.preventDefault()
    if (!chatInput.trim() || sending) return

    if (killSwitchActive) {
      showToast('Action halted: Assistant engine is paused by the emergency kill switch.')
      return
    }

    const textToSend = chatInput.trim()
    setChatInput('')

    let targetConvId = activeConvId
    if (!targetConvId) {
      // Create conversation on the fly
      const title = textToSend.substring(0, 30) + (textToSend.length > 30 ? '...' : '')
      const newConv = await createConversation(effectiveWorkspaceId, title)
      targetConvId = newConv.conversation.id
      setActiveConvId(targetConvId)
      setConversations(prev => [newConv.conversation, ...prev])
    }

    // Optimistic UI update
    const tempUserMsg = {
      id: `temp_${Date.now()}`,
      role: 'user',
      content: textToSend,
      created_at: new Date().toISOString()
    }
    setMessages(prev => [...prev, tempUserMsg])
    setSending(true)

    try {
      const res = await sendChatMessage(targetConvId, textToSend, killSwitchActive)
      if (res.assistant_message) {
        setMessages(prev => [
          ...prev.filter(m => m.id !== tempUserMsg.id),
          res.user_message,
          res.assistant_message
        ])
        let meta = res.assistant_message.metadata
        if (typeof meta === 'string') {
          try { meta = JSON.parse(meta) } catch { meta = null }
        }
        if (meta && (meta.tool_executed || meta.approval_required)) {
          window.dispatchEvent(new CustomEvent('pa:data-changed'))
        }
      }
    } catch (err) {
      showToast(err.message || 'Error communicating with assistant.')
    } finally {
      setSending(false)
    }
  }

  // Handle Enter key vs Shift+Enter
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  // Create Workspace
  const handleCreateWorkspace = async (e) => {
    e.preventDefault()
    if (!newWsName.trim()) return

    setCreatingWs(true)
    try {
      const res = await createUserWorkspace({
        name: newWsName.trim(),
        type: newWsType,
        description: newWsDesc.trim() || 'Custom user workspace.'
      })
      setIsCreatingWs(false)
      setNewWsName('')
      setNewWsDesc('')
      showToast(`Created workspace: "${newWsName.trim()}"`)
      if (onWorkspacesChanged) onWorkspacesChanged()
      if (res.id) {
        setActiveWsId(res.id)
        if (setActiveWorkspaceId) setActiveWorkspaceId(res.id)
      }
    } catch {
      showToast('Failed to create workspace.')
    } finally {
      setCreatingWs(false)
    }
  }

  // Add Note to Workspace
  const handleAddWorkspaceNote = async (e) => {
    e.preventDefault()
    if (!noteTitle.trim() || !noteContent.trim() || !currentWs) return

    setSavingNote(true)
    try {
      const data = await createWorkspaceNote(currentWs.id, noteTitle.trim(), noteContent.trim())
      if (data.note) {
        setWorkspaceNotes(prev => [data.note, ...prev])
        showToast('Note saved to workspace context.')
        setIsAddingNote(false)
        setNoteTitle('')
        setNoteContent('')
      }
    } catch {
      showToast('Failed to save workspace note.')
    } finally {
      setSavingNote(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* Privacy & Sandbox Boundary Header */}
      <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 rounded-xl bg-[#D5E0BD]/50 border border-[#D5E0BD] p-2.5 text-[#171717]">
            <Lock className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-[#242424]">
                {isMainChatOnly ? 'Central Assistant Chat' : `Workspace: ${currentWs?.name || 'Workspace'}`}
              </h2>
              <span className="rounded bg-[#D5E0BD]/60 px-2 py-0.5 text-[10px] font-mono font-medium text-[#171717]">
                Sandbox Enforced
              </span>
              {killSwitchActive && (
                <span className="rounded bg-[#EBC1D9] border border-[#EBC1D9] px-2 py-0.5 text-[10px] font-mono font-semibold text-[#171717]">
                  Halted by Kill Switch
                </span>
              )}
            </div>
            <p className="text-xs text-[#6B7280] mt-0.5">
              {isMainChatOnly
                ? 'General personal assistant for scheduling, inbox questions, and supervisory overview.'
                : 'Isolated project context: Messages, notes, and tasks in this workspace remain isolated from other projects.'}
            </p>
          </div>
        </div>

        {!isMainChatOnly && (
          <button
            onClick={() => setIsCreatingWs(true)}
            className="inline-flex items-center gap-1.5 rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] px-3.5 py-2 text-xs font-semibold text-[#242424] hover:bg-[#EFECE2] hover:border-[#242424] transition-all shrink-0 cursor-pointer shadow-warm-sm self-start md:self-auto"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>New Workspace</span>
          </button>
        )}
      </div>

      {/* Workspace Creation Modal */}
      {isCreatingWs && (
        <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-6 space-y-4 shadow-warm-md animate-in fade-in duration-150">
          <div className="flex items-center justify-between border-b border-[#DEDAD0] pb-3">
            <h3 className="text-sm font-semibold text-[#242424]">Create Isolated Project Workspace</h3>
            <button
              onClick={() => setIsCreatingWs(false)}
              className="text-xs text-[#6B7280] hover:text-[#242424] cursor-pointer"
            >
              Cancel
            </button>
          </div>

          <form onSubmit={handleCreateWorkspace} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-[#242424]">Workspace Name</label>
                <input
                  type="text"
                  required
                  value={newWsName}
                  onChange={(e) => setNewWsName(e.target.value)}
                  placeholder="e.g. Physics Exam Prep or Architecture Review"
                  className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-[#242424]">Category Scope</label>
                <select
                  value={newWsType}
                  onChange={(e) => setNewWsType(e.target.value)}
                  className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
                >
                  <option value="Project">Project Workspace</option>
                  <option value="Study">Study & Exam Workspace</option>
                  <option value="Notes">Notes & Research</option>
                  <option value="General">General Workspace</option>
                </select>
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-[#242424]">Context Objective</label>
              <input
                type="text"
                value={newWsDesc}
                onChange={(e) => setNewWsDesc(e.target.value)}
                placeholder="What is the focus of this workspace?"
                className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-[#DEDAD0]">
              <button
                type="button"
                onClick={() => setIsCreatingWs(false)}
                className="rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] px-3.5 py-1.5 text-xs font-medium text-[#6B7280] hover:text-[#242424]"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={creatingWs || !newWsName.trim()}
                className="rounded-xl bg-[#242424] px-4 py-1.5 text-xs font-semibold text-[#FFFDF8] hover:bg-[#383838] transition-colors disabled:opacity-30 cursor-pointer shadow-warm-sm"
              >
                {creatingWs ? 'Creating...' : 'Create Workspace'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Main 3-Column / 2-Column Split Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 min-h-[640px]">
        {/* Left Column: Workspaces List & Workspace Context (3 of 12 columns, hidden if isMainChatOnly) */}
        {!isMainChatOnly && (
          <div className="lg:col-span-3 rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-4 shadow-warm-sm flex flex-col justify-between space-y-4">
            <div className="space-y-4 overflow-y-auto">
              <div className="flex items-center justify-between border-b border-[#DEDAD0] pb-2 text-xs">
                <span className="font-semibold text-[#242424]">Workspaces</span>
                <span className="font-mono text-[11px] text-[#6B7280]">{workspaces.length}</span>
              </div>

              {/* Workspaces List */}
              <div className="space-y-1.5">
                {workspaces.map((ws) => {
                  const isCurrent = (activeWorkspaceId || activeWsId) === ws.id
                  return (
                    <button
                      key={ws.id}
                      onClick={() => {
                        setActiveWsId(ws.id)
                        if (setActiveWorkspaceId) setActiveWorkspaceId(ws.id)
                      }}
                      className={`w-full text-left p-3 rounded-xl border text-xs transition-all cursor-pointer ${
                        isCurrent
                          ? 'border-[#242424] bg-[#F7F4EB] text-[#242424] shadow-warm-sm'
                          : 'border-[#DEDAD0] bg-[#FFFDF8] text-[#4B5563] hover:bg-[#F7F4EB]/50'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold truncate">{ws.name}</span>
                        <ChevronRight className="h-3.5 w-3.5 text-[#9CA3AF]" />
                      </div>
                      <div className="text-[10px] text-[#6B7280] truncate mt-0.5">
                        {ws.type} • {ws.description || 'Isolated sandbox'}
                      </div>
                    </button>
                  )
                })}
              </div>

              {/* Workspace Notes Context Section */}
              {currentWs && (
                <div className="pt-2 border-t border-[#DEDAD0] space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-[#242424] flex items-center gap-1.5">
                      <StickyNote className="h-3.5 w-3.5 text-[#6B7280]" />
                      Workspace Notes
                    </span>
                    <button
                      onClick={() => setIsAddingNote(true)}
                      className="text-[11px] font-semibold text-[#242424] hover:underline cursor-pointer"
                    >
                      + Note
                    </button>
                  </div>

                  {isAddingNote && (
                    <form onSubmit={handleAddWorkspaceNote} className="space-y-2 p-2.5 rounded-xl border border-[#DEDAD0] bg-[#F7F4EB]">
                      <input
                        type="text"
                        required
                        value={noteTitle}
                        onChange={(e) => setNoteTitle(e.target.value)}
                        placeholder="Note Title"
                        className="w-full rounded-lg border border-[#DEDAD0] bg-[#FFFDF8] p-1.5 text-xs text-[#242424] focus:outline-none"
                      />
                      <textarea
                        rows={2}
                        required
                        value={noteContent}
                        onChange={(e) => setNoteContent(e.target.value)}
                        placeholder="Context content..."
                        className="w-full rounded-lg border border-[#DEDAD0] bg-[#FFFDF8] p-1.5 text-xs text-[#242424] focus:outline-none"
                      />
                      <div className="flex justify-end gap-1.5">
                        <button
                          type="button"
                          onClick={() => setIsAddingNote(false)}
                          className="px-2 py-0.5 text-[10px] text-[#6B7280]"
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          disabled={savingNote}
                          className="px-2.5 py-0.5 rounded bg-[#242424] text-[10px] font-semibold text-[#FFFDF8]"
                        >
                          Save
                        </button>
                      </div>
                    </form>
                  )}

                  <div className="space-y-1.5 max-h-40 overflow-y-auto">
                    {workspaceNotes.length === 0 ? (
                      <p className="text-[11px] text-[#9CA3AF] italic">No notes in this workspace context.</p>
                    ) : (
                      workspaceNotes.map(n => (
                        <div key={n.id} className="p-2 rounded-lg border border-[#DEDAD0] bg-[#F7F4EB]/50 text-xs">
                          <div className="font-semibold text-[#242424] text-[11px]">{n.title}</div>
                          <div className="text-[10px] text-[#6B7280] line-clamp-2 mt-0.5">{n.content}</div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>

            <div className="p-3 rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] text-[11px] text-[#6B7280] flex items-center gap-2">
              <Lock className="h-3.5 w-3.5 shrink-0" />
              <span>Boundary: Notes and history remain strictly inside this workspace.</span>
            </div>
          </div>
        )}

        {/* Middle Column: Conversations List (3 of 12 columns if workspace mode, 4 of 12 if main chat) */}
        <div className={`${!isMainChatOnly ? 'lg:col-span-3' : 'lg:col-span-4'} rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-4 shadow-warm-sm flex flex-col justify-between space-y-3`}>
          <div className="space-y-3 overflow-y-auto flex-1">
            <div className="flex items-center justify-between border-b border-[#DEDAD0] pb-2 text-xs">
              <span className="font-semibold text-[#242424]">Conversations</span>
              <button
                onClick={handleNewConversation}
                className="inline-flex items-center gap-1 rounded-lg border border-[#DEDAD0] bg-[#F7F4EB] px-2.5 py-1 text-[11px] font-semibold text-[#242424] hover:bg-[#EFECE2] transition-colors cursor-pointer shadow-warm-sm"
              >
                <Plus className="h-3 w-3" />
                <span>New Chat</span>
              </button>
            </div>

            {loadingConversations ? (
              <div className="py-12 text-center text-xs text-[#6B7280]">
                <RefreshCw className="mx-auto h-4 w-4 animate-spin mb-1 text-[#242424]" />
                Loading conversations...
              </div>
            ) : conversations.length === 0 ? (
              <div className="py-12 text-center text-xs text-[#6B7280]">
                No conversation history yet. Start a new chat!
              </div>
            ) : (
              <div className="space-y-1">
                {conversations.map((conv) => {
                  const isSelected = activeConvId === conv.id
                  return (
                    <div
                      key={conv.id}
                      onClick={() => loadMessages(conv.id)}
                      className={`group p-2.5 rounded-xl border transition-all cursor-pointer flex items-center justify-between text-xs ${
                        isSelected
                          ? 'border-[#242424] bg-[#F7F4EB] text-[#242424] font-medium shadow-warm-sm'
                          : 'border-transparent text-[#4B5563] hover:bg-[#F7F4EB]/50'
                      }`}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <MessageSquare className="h-3.5 w-3.5 shrink-0 text-[#9CA3AF]" />
                        <span className="truncate">{conv.title || 'Conversation'}</span>
                      </div>

                      <button
                        onClick={(e) => handleDeleteConversation(conv.id, e)}
                        title="Delete conversation"
                        className="opacity-0 group-hover:opacity-100 p-1 text-[#9CA3AF] hover:text-[#B91C1C] transition-opacity"
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          <div className="text-[11px] text-[#9CA3AF] font-mono border-t border-[#DEDAD0] pt-2">
            Context: {isMainChatOnly ? 'General Assistant' : (currentWs?.name || 'Workspace')}
          </div>
        </div>

        {/* Right Column: Active Conversation Stream & Message Composer (6 of 12 columns if workspace mode, 8 of 12 if main chat) */}
        <div className={`${!isMainChatOnly ? 'lg:col-span-6' : 'lg:col-span-8'} rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] shadow-warm-sm flex flex-col justify-between overflow-hidden min-h-[550px]`}>
          {/* Conversation Stream */}
          <div className="flex-1 overflow-y-auto p-5 sm:p-6 space-y-4 bg-[#FFFDF8]">
            {loadingMessages ? (
              <div className="py-24 text-center text-xs text-[#6B7280]">
                <RefreshCw className="mx-auto h-5 w-5 animate-spin mb-1 text-[#242424]" />
                Retrieving conversation stream...
              </div>
            ) : messages.length === 0 ? (
              <div className="py-24 text-center text-xs text-[#6B7280] space-y-2">
                <Bot className="mx-auto h-8 w-8 text-[#9CA3AF]" />
                <p className="font-semibold text-[#242424]">
                  {isMainChatOnly ? 'Central AI Assistant' : `${currentWs?.name || 'Workspace'} Chat`}
                </p>
                <p className="max-w-sm mx-auto text-[11px]">
                  Ask questions, summarize incoming emails, plan projects, or manage tasks in supervised mode.
                </p>
              </div>
            ) : (
              messages.map((msg, idx) => {
                const isAssistant = msg.role === 'assistant'
                let metadata = null
                try {
                  if (msg.metadata) metadata = JSON.parse(msg.metadata)
                } catch {
                  metadata = null
                }

                return (
                  <div
                    key={msg.id || idx}
                    className={`flex gap-3 max-w-2xl ${isAssistant ? '' : 'ml-auto flex-row-reverse'}`}
                  >
                    <div
                      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border text-xs shadow-warm-sm ${
                        isAssistant
                          ? 'bg-[#242424] text-[#FFFDF8] border-[#242424]'
                          : 'bg-[#F7F4EB] text-[#242424] border-[#DEDAD0]'
                      }`}
                    >
                      {isAssistant ? <Bot className="h-4 w-4" /> : <User className="h-4 w-4" />}
                    </div>

                    <div className="space-y-1.5 max-w-[85%]">
                      <div
                        className={`rounded-2xl p-4 text-xs leading-relaxed shadow-warm-sm ${
                          isAssistant
                            ? 'bg-[#FFFDF8] border border-[#DEDAD0] text-[#242424]'
                            : 'bg-[#242424] text-[#FFFDF8]'
                        }`}
                      >
                        {formatMessageContent(msg.content, isAssistant)}
                      </div>

                      {/* Tool Execution or Policy Status Badge */}
                      {metadata && metadata.tool_executed && (
                        <div className={`flex items-center gap-1.5 text-[10px] font-mono px-2 py-0.5 rounded-lg w-fit border ${
                          (metadata.policy_decision || '').includes('Refused') || (metadata.policy_decision || '').includes('Conflict')
                            ? 'bg-[#E9DB91]/30 border-[#E9DB91] text-[#854D0E]'
                            : 'bg-[#D5E0BD]/30 border-[#D5E0BD] text-[#42542B]'
                        }`}>
                          {(metadata.policy_decision || '').includes('Refused') || (metadata.policy_decision || '').includes('Conflict') ? (
                            <AlertTriangle className="h-3 w-3 shrink-0" />
                          ) : (
                            <CheckCircle2 className="h-3 w-3 shrink-0" />
                          )}
                          <span>Tool: {metadata.tool_executed}</span>
                          <span>•</span>
                          <span className="font-semibold">{metadata.policy_decision}</span>
                        </div>
                      )}

                      {metadata && metadata.approval_required && (
                        <div className="flex items-center gap-1.5 text-[10px] font-mono text-[#854D0E] bg-[#E9DB91]/40 border border-[#E9DB91] px-2 py-0.5 rounded-lg w-fit">
                          <ShieldAlert className="h-3 w-3 shrink-0" />
                          <span>Action Staged in Approvals Queue</span>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })
            )}

            {sending && (
              <div className="flex gap-3 max-w-2xl">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-[#242424] text-[#FFFDF8] border border-[#242424] shadow-warm-sm">
                  <Bot className="h-4 w-4" />
                </div>
                <div className="rounded-2xl p-4 text-xs bg-[#FFFDF8] border border-[#DEDAD0] text-[#6B7280] flex items-center gap-2">
                  <RefreshCw className="h-3.5 w-3.5 animate-spin text-[#242424]" />
                  <span>Reasoning and checking policy gate...</span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Message Composer Area */}
          <div className="p-4 border-t border-[#DEDAD0] bg-[#FFFDF8]">
            <form onSubmit={handleSendMessage} className="space-y-2">
              <div className="relative">
                <textarea
                  rows={2}
                  value={chatInput}
                  disabled={sending || killSwitchActive}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={
                    killSwitchActive
                      ? 'Assistant engine is paused by emergency kill switch...'
                      : 'Ask a question or request an action (e.g. "create task Review Section 3 tomorrow", "check emails")... Press Enter to send, Shift+Enter for new line.'
                  }
                  className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] py-2.5 pl-3.5 pr-12 text-xs text-[#242424] placeholder:text-[#9CA3AF] focus:border-[#242424] focus:bg-[#FFFDF8] focus:outline-none transition-all resize-none disabled:opacity-50"
                />

                <button
                  type="submit"
                  disabled={!chatInput.trim() || sending || killSwitchActive}
                  className="absolute right-2.5 bottom-3.5 rounded-xl bg-[#242424] p-2 text-[#FFFDF8] hover:bg-[#383838] transition-colors disabled:opacity-30 cursor-pointer shadow-warm-sm"
                  title="Send message"
                >
                  <Send className="h-3.5 w-3.5" />
                </button>
              </div>

              <div className="flex items-center justify-between text-[11px] text-[#9CA3AF]">
                <span>Press <strong>Enter</strong> to send, <strong>Shift + Enter</strong> for line break</span>
                <span className="font-mono">Supervised Execution</span>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}
