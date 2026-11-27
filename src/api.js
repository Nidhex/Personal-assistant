// Frontend API client for backend authentication and Gmail operations

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

async function apiFetch(url, options = {}) {
  const fullUrl = url.startsWith('/') ? `${API_BASE}${url}` : url
  const headers = { ...(options.headers || {}) }

  // Dual cookie/bearer session token support (for mobile and cross-origin resilience)
  try {
    const token = typeof window !== 'undefined' ? localStorage.getItem('deskagent_session_id') : null
    if (token && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${token}`
    }
  } catch {}

  const opts = {
    credentials: 'include',
    ...options,
    headers
  }
  return fetch(fullUrl, opts)
}


export async function checkAuthStatus() {
  try {
    const res = await apiFetch('/api/auth/status')
    if (!res.ok) throw new Error('Failed to fetch auth status')
    return await res.json()
  } catch (err) {
    return {
      google_configured: false,
      dev_test_mode_enabled: false,
      missing_keys: ['GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET'],
      error: err.message
    }
  }
}

export async function fetchCurrentUser() {
  try {
    const res = await apiFetch('/api/auth/me')
    if (!res.ok) return { authenticated: false, user: null, gmail_connected: false }
    return await res.json()
  } catch (err) {
    return { authenticated: false, user: null, gmail_connected: false, error: err.message }
  }
}

export async function getGoogleAuthUrl() {
  const res = await apiFetch('/api/auth/google/url')
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to generate Google authentication URL')
  }
  return await res.json()
}

export async function logoutUser() {
  try {
    try {
      if (typeof window !== 'undefined') localStorage.removeItem('deskagent_session_id')
    } catch {}
    const res = await apiFetch('/api/auth/logout', { method: 'POST' })
    return await res.json()
  } catch (err) {
    return { success: false, error: err.message }
  }
}

export async function devLogin(email = 'developer@test.local', name = 'Test User') {
  const res = await apiFetch('/api/auth/dev-login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, name })
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Dev login failed')
  }
  return await res.json()
}

export async function fetchGmailMessages(pageToken = null, maxResults = 15) {
  const params = new URLSearchParams()
  params.set('max_results', maxResults.toString())
  if (pageToken) params.set('page_token', pageToken)

  const res = await apiFetch(`/api/gmail/messages?${params.toString()}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to fetch messages from Gmail')
  }
  return await res.json()
}

export async function fetchGmailMessageDetail(messageId) {
  const res = await apiFetch(`/api/gmail/messages/${messageId}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to fetch email message details')
  }
  return await res.json()
}

export async function disconnectGmail() {
  const res = await apiFetch('/api/gmail/disconnect', { method: 'POST' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to disconnect Gmail')
  }
  return await res.json()
}

export async function fetchUserData() {
  try {
    const res = await apiFetch('/api/user/data')
    if (!res.ok) return { tasks: [], workspaces: [], approvals: [], activity: [] }
    return await res.json()
  } catch {
    return { tasks: [], workspaces: [], approvals: [], activity: [] }
  }
}

export async function createUserTask(task) {
  const res = await apiFetch('/api/user/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(task)
  })
  if (!res.ok) throw new Error('Failed to create task')
  return await res.json()
}

export async function proposeTaskFromEmail(messageId) {
  const res = await apiFetch(`/api/gmail/messages/${encodeURIComponent(messageId)}/propose-task`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to propose task from email')
  }
  return await res.json()
}

export async function toggleUserTask(taskId) {
  const res = await apiFetch(`/api/user/tasks/${taskId}/toggle`, { method: 'POST' })
  if (!res.ok) throw new Error('Failed to update task')
  return await res.json()
}

export async function updateUserTask(taskId, updates) {
  const res = await apiFetch(`/api/user/tasks/${encodeURIComponent(taskId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates)
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to update task')
  }
  return await res.json()
}

export async function deleteUserTask(taskId) {
  const res = await apiFetch(`/api/user/tasks/${encodeURIComponent(taskId)}`, {
    method: 'DELETE'
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to delete task')
  }
  return await res.json()
}

export async function fetchYouTubeNotes(url) {
  const res = await apiFetch('/api/youtube/notes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url })
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const err = new Error(data.detail || 'Failed to retrieve YouTube captions')
    err.code = data.code || 'YOUTUBE_NOTES_FAILED'
    err.status = res.status
    throw err
  }
  return data
}

export async function createUserWorkspace(ws) {
  const res = await apiFetch('/api/user/workspaces', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(ws)
  })
  if (!res.ok) throw new Error('Failed to create workspace')
  return await res.json()
}

export async function handleApprovalActionApi(approvalId, action) {
  const res = await apiFetch(`/api/user/approvals/${approvalId}/action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action })
  })
  if (!res.ok) throw new Error('Failed to process approval action')
  return await res.json()
}

// -------------------------------------------------------------
// CHAT & CONVERSATION API (PERSISTENT & WORKSPACE ISOLATED)
// -------------------------------------------------------------
export async function fetchConversations(workspaceId = null) {
  const url = workspaceId && workspaceId !== 'main'
    ? `/api/chat/conversations?workspace_id=${encodeURIComponent(workspaceId)}`
    : '/api/chat/conversations'
  const res = await apiFetch(url)
  if (!res.ok) return { conversations: [] }
  return await res.json()
}

export async function createConversation(workspaceId = null, title = 'New Conversation') {
  const res = await apiFetch('/api/chat/conversations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace_id: workspaceId, title })
  })
  if (!res.ok) throw new Error('Failed to create conversation')
  return await res.json()
}

export async function fetchConversationMessages(conversationId) {
  const res = await apiFetch(`/api/chat/conversations/${conversationId}/messages`)
  if (!res.ok) throw new Error('Failed to load conversation messages')
  return await res.json()
}

export async function sendChatMessage(conversationId, content, killSwitchActive = false) {
  const res = await apiFetch(`/api/chat/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, kill_switch_active: killSwitchActive })
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to send message')
  }
  return await res.json()
}

export async function deleteConversation(conversationId) {
  const res = await apiFetch(`/api/chat/conversations/${conversationId}`, {
    method: 'DELETE'
  })
  if (!res.ok) throw new Error('Failed to delete conversation')
  return await res.json()
}

export async function fetchWorkspaceNotes(workspaceId) {
  const res = await apiFetch(`/api/user/workspaces/${workspaceId}/notes`)
  if (!res.ok) return { notes: [] }
  return await res.json()
}

export async function createWorkspaceNote(workspaceId, title, content) {
  const res = await apiFetch(`/api/user/workspaces/${workspaceId}/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, content })
  })
  if (!res.ok) throw new Error('Failed to save note')
  return await res.json()
}

// -------------------------------------------------------------
// CALENDAR API
// -------------------------------------------------------------
export async function fetchCalendarEvents(date = null) {
  const url = date ? `/api/user/calendar/events?date=${encodeURIComponent(date)}` : '/api/user/calendar/events'
  const res = await apiFetch(url)
  if (!res.ok) return { events: [] }
  return await res.json()
}

export async function createCalendarEvent(eventData) {
  const res = await apiFetch('/api/user/calendar/events', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(eventData)
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to create calendar event')
  }
  return await res.json()
}

export async function updateCalendarEvent(eventId, eventData) {
  const res = await apiFetch(`/api/user/calendar/events/${eventId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(eventData)
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to update calendar event')
  }
  return await res.json()
}

export async function deleteCalendarEvent(eventId) {
  const res = await apiFetch(`/api/user/calendar/events/${eventId}`, {
    method: 'DELETE'
  })
  if (!res.ok) throw new Error('Failed to delete calendar event')
  return await res.json()
}

// -------------------------------------------------------------
// STUDY MATERIALS & REVISION PLAN API
// -------------------------------------------------------------
export async function fetchWorkspaceStudyMaterials(workspaceId) {
  const res = await apiFetch(`/api/user/workspaces/${workspaceId}/study-materials`)
  if (!res.ok) return { materials: [] }
  return await res.json()
}

export async function uploadStudyMaterial(workspaceId, filename, contentText) {
  const res = await apiFetch(`/api/user/workspaces/${workspaceId}/study-materials`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename, content_text: contentText })
  })
  if (!res.ok) throw new Error('Failed to upload study material')
  return await res.json()
}

export async function fetchWorkspaceRevisionPlan(workspaceId) {
  const res = await apiFetch(`/api/user/workspaces/${workspaceId}/revision-plan`)
  if (!res.ok) return { plan: null }
  return await res.json()
}

// -------------------------------------------------------------
// DAILY RUNS, DIGESTS & SCHEDULER API
// -------------------------------------------------------------
export async function fetchAgentSettings() {
  const res = await apiFetch('/api/agent/settings')
  if (!res.ok) return { settings: null }
  return await res.json()
}

export async function updateAgentSettings(settings) {
  const res = await apiFetch('/api/agent/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings)
  })
  if (!res.ok) throw new Error('Failed to update agent settings')
  return await res.json()
}

export async function setKillSwitchApi(enabled) {
  const res = await apiFetch('/api/agent/kill-switch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled })
  })
  if (!res.ok) throw new Error('Failed to toggle kill switch')
  return await res.json()
}

export async function triggerManualAgentRun() {
  const res = await apiFetch('/api/agent/runs/trigger', {
    method: 'POST'
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to trigger agent run')
  }
  return await res.json()
}

export async function fetchAgentRuns() {
  const res = await apiFetch('/api/agent/runs')
  if (!res.ok) return { runs: [] }
  return await res.json()
}

export async function fetchAgentRunSteps(runId) {
  const res = await apiFetch(`/api/agent/runs/${runId}/steps`)
  if (!res.ok) throw new Error('Failed to fetch run execution steps')
  return await res.json()
}

export async function fetchLatestDailyDigest() {
  const res = await apiFetch('/api/agent/digests/latest')
  if (!res.ok) return { digest: null }
  return await res.json()
}

export async function fetchDailyDigests() {
  const res = await apiFetch('/api/agent/digests')
  if (!res.ok) return { digests: [] }
  return await res.json()
}

