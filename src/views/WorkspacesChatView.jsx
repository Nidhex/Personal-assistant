import React, { useState } from 'react'
import {
  Lock,
  Plus,
  Send,
  Bot,
  User,
  FolderOpen,
  ChevronRight
} from 'lucide-react'
import { createUserWorkspace } from '../api'

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
    activeWorkspaceId || (workspaces[0] ? workspaces[0].id : '')
  )
  const [chatMessage, setChatMessage] = useState('')
  const [isCreatingWs, setIsCreatingWs] = useState(false)
  const [newWsName, setNewWsName] = useState('')
  const [newWsType, setNewWsType] = useState('Research & Notes')
  const [newWsDesc, setNewWsDesc] = useState('')
  const [creating, setCreating] = useState(false)

  // Determine current active workspace
  const currentWs = !isMainChatOnly
    ? workspaces.find(w => w.id === (activeWorkspaceId || activeWsId)) || workspaces[0] || null
    : null

  // Messages state
  const [chatMessages, setChatMessages] = useState([
    {
      sender: 'assistant',
      text: isMainChatOnly
        ? 'Good day. I am your personal supervisory AI assistant. You can ask questions about your schedule, summarize emails, or create new isolated project workspaces.'
        : `Welcome to the "${currentWs?.name || 'Project'}" workspace. Notes, uploaded files, and context in this workspace remain isolated from other projects.`
    }
  ])

  const handleSendMessage = (e) => {
    e.preventDefault()
    if (!chatMessage.trim()) return
    if (killSwitchActive) {
      showToast('Engine halted by emergency kill switch. Cannot send message.')
      return
    }

    const userText = chatMessage.trim()
    setChatMessage('')

    setChatMessages(prev => [
      ...prev,
      { sender: 'user', text: userText },
      {
        sender: 'assistant',
        text: `Received: "${userText}". Processing in supervised mode. All actions requiring external modification will appear in your Approvals inbox.`
      }
    ])
  }

  const handleCreateWorkspace = async (e) => {
    e.preventDefault()
    if (!newWsName.trim()) return

    setCreating(true)
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
      setCreating(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* Privacy & Sandbox Boundary Header */}
      <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 rounded-lg bg-[#D5E0BD]/50 border border-[#D5E0BD] p-2 text-[#171717]">
            <Lock className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-[#242424]">
                {isMainChatOnly ? 'Main Chat Assistant' : `Workspace: ${currentWs?.name || 'Workspace'}`}
              </h2>
              <span className="rounded bg-[#D5E0BD]/60 px-2 py-0.5 text-[10px] font-mono font-medium text-[#171717]">
                Sandbox Enforced
              </span>
            </div>
            <p className="text-xs text-[#6B7280] mt-0.5">
              Strict isolation boundary: Notes, conversation history, and uploaded files cannot cross workspace boundaries without explicit user export.
            </p>
          </div>
        </div>

        {!isMainChatOnly && (
          <button
            onClick={() => setIsCreatingWs(true)}
            className="inline-flex items-center gap-1.5 rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] px-3.5 py-2 text-xs font-semibold text-[#242424] hover:bg-[#EFECE2] hover:border-[#242424] transition-all shrink-0 cursor-pointer shadow-warm-sm"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>New Workspace</span>
          </button>
        )}
      </div>

      {/* Workspace Creation Modal Form */}
      {isCreatingWs && (
        <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-6 space-y-4 shadow-warm-md animate-in fade-in duration-150">
          <div className="flex items-center justify-between border-b border-[#DEDAD0] pb-3">
            <h3 className="text-sm font-semibold text-[#242424]">Create New Sandboxed Workspace</h3>
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
                <label className="text-xs font-medium text-[#242424]">Workspace Title</label>
                <input
                  type="text"
                  value={newWsName}
                  onChange={(e) => setNewWsName(e.target.value)}
                  placeholder="e.g. Systems Architecture Review"
                  className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-[#242424]">Category Scope</label>
                <select
                  value={newWsType}
                  onChange={(e) => setNewWsType(e.target.value)}
                  className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
                >
                  <option value="Research & Notes">Research & Notes</option>
                  <option value="Project Planning">Project Planning</option>
                  <option value="Writing & Papers">Writing & Papers</option>
                  <option value="General">General</option>
                </select>
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-[#242424]">Context Summary / Objective</label>
              <input
                type="text"
                value={newWsDesc}
                onChange={(e) => setNewWsDesc(e.target.value)}
                placeholder="Brief goal of this workspace..."
                className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setIsCreatingWs(false)}
                className="rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] px-3.5 py-1.5 text-xs font-medium text-[#6B7280] hover:text-[#242424]"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={creating || !newWsName.trim()}
                className="rounded-xl bg-[#242424] px-4 py-1.5 text-xs font-semibold text-[#FFFDF8] hover:bg-[#383838] disabled:opacity-30 cursor-pointer"
              >
                {creating ? 'Creating...' : 'Create Workspace'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Main Chat & Workspace Split Area */}
      <div className={`grid grid-cols-1 ${!isMainChatOnly ? 'lg:grid-cols-12' : ''} gap-4 min-h-[580px]`}>
        {/* Left Side: Workspaces Selector & Workspace Notes (if in Workspaces mode) */}
        {!isMainChatOnly && (
          <div className="lg:col-span-4 rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-4 shadow-warm-sm flex flex-col space-y-4">
            <div className="flex items-center justify-between border-b border-[#DEDAD0] pb-2 text-xs">
              <span className="font-semibold text-[#242424]">Your Workspaces</span>
              <span className="font-mono text-[11px] text-[#6B7280]">{workspaces.length} Total</span>
            </div>

            <div className="space-y-1.5 overflow-y-auto flex-1">
              {workspaces.length === 0 ? (
                <div className="py-8 text-center text-xs text-[#6B7280]">
                  No workspaces created yet. Click "New Workspace" to create an isolated project context.
                </div>
              ) : (
                workspaces.map((ws) => {
                  const isCurrent = (activeWorkspaceId || activeWsId) === ws.id
                  return (
                    <button
                      key={ws.id}
                      onClick={() => {
                        setActiveWsId(ws.id)
                        if (setActiveWorkspaceId) setActiveWorkspaceId(ws.id)
                      }}
                      className={`w-full text-left p-3 rounded-xl border text-xs transition-all ${
                        isCurrent
                          ? 'border-[#242424] bg-[#F7F4EB] text-[#242424]'
                          : 'border-[#DEDAD0] bg-[#FFFDF8] text-[#4B5563] hover:bg-[#F7F4EB]/50'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold truncate">{ws.name}</span>
                        <ChevronRight className="h-3.5 w-3.5 text-[#9CA3AF]" />
                      </div>
                      <div className="text-[11px] text-[#6B7280] truncate mt-0.5">
                        {ws.description || ws.type}
                      </div>
                    </button>
                  )
                })
              )}
            </div>

            {/* Sandboxed Notes & Files Summary */}
            <div className="p-3 rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] text-xs space-y-2">
              <div className="flex items-center gap-1.5 font-semibold text-[#242424]">
                <FolderOpen className="h-3.5 w-3.5" />
                <span>Workspace Context</span>
              </div>
              <p className="text-[11px] text-[#6B7280] leading-snug">
                {currentWs ? `Boundary: ${currentWs.name}` : 'Main General Context'}
              </p>
            </div>
          </div>
        )}

        {/* Right Side / Full Width: Chat Conversation & Message Composer */}
        <div className={`${!isMainChatOnly ? 'lg:col-span-8' : 'w-full'} rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] shadow-warm-sm flex flex-col overflow-hidden`}>
          {/* Conversation Stream */}
          <div className="flex-1 overflow-y-auto p-5 sm:p-6 space-y-4 bg-[#FFFDF8]">
            {chatMessages.map((msg, idx) => {
              const isAssistant = msg.sender === 'assistant'
              return (
                <div
                  key={idx}
                  className={`flex gap-3 max-w-2xl ${isAssistant ? '' : 'ml-auto flex-row-reverse'}`}
                >
                  <div
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border text-xs ${
                      isAssistant
                        ? 'bg-[#242424] text-[#FFFDF8] border-[#242424]'
                        : 'bg-[#F7F4EB] text-[#242424] border-[#DEDAD0]'
                    }`}
                  >
                    {isAssistant ? <Bot className="h-4 w-4" /> : <User className="h-4 w-4" />}
                  </div>

                  <div
                    className={`rounded-2xl p-4 text-xs leading-relaxed ${
                      isAssistant
                        ? 'bg-[#F7F4EB] border border-[#DEDAD0] text-[#242424]'
                        : 'bg-[#242424] text-[#FFFDF8]'
                    }`}
                  >
                    {msg.text}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Message Composer */}
          <div className="p-4 border-t border-[#DEDAD0] bg-[#FFFDF8]">
            <form onSubmit={handleSendMessage} className="relative">
              <input
                type="text"
                value={chatMessage}
                disabled={killSwitchActive}
                onChange={(e) => setChatMessage(e.target.value)}
                placeholder={
                  killSwitchActive
                    ? 'Engine halted by kill switch...'
                    : 'Message your assistant in supervised mode...'
                }
                className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] py-3 pl-4 pr-12 text-xs text-[#242424] placeholder:text-[#9CA3AF] focus:border-[#242424] focus:bg-[#FFFDF8] focus:outline-none transition-all disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={!chatMessage.trim() || killSwitchActive}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg bg-[#242424] p-2 text-[#FFFDF8] hover:bg-[#383838] transition-colors disabled:opacity-30 cursor-pointer"
              >
                <Send className="h-3.5 w-3.5" />
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}
