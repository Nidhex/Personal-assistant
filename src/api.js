// Frontend API client for backend authentication and Gmail operations

export async function checkAuthStatus() {
  try {
    const res = await fetch('/api/auth/status')
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
    const res = await fetch('/api/auth/me')
    if (!res.ok) return { authenticated: false, user: null, gmail_connected: false }
    return await res.json()
  } catch (err) {
    return { authenticated: false, user: null, gmail_connected: false, error: err.message }
  }
}

export async function getGoogleAuthUrl() {
  const res = await fetch('/api/auth/google/url')
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to generate Google authentication URL')
  }
  return await res.json()
}

export async function logoutUser() {
  try {
    const res = await fetch('/api/auth/logout', { method: 'POST' })
    return await res.json()
  } catch (err) {
    return { success: false, error: err.message }
  }
}

export async function devLogin(email = 'developer@test.local', name = 'Test User') {
  const res = await fetch('/api/auth/dev-login', {
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

  const res = await fetch(`/api/gmail/messages?${params.toString()}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to fetch messages from Gmail')
  }
  return await res.json()
}

export async function fetchGmailMessageDetail(messageId) {
  const res = await fetch(`/api/gmail/messages/${messageId}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to fetch email message details')
  }
  return await res.json()
}

export async function disconnectGmail() {
  const res = await fetch('/api/gmail/disconnect', { method: 'POST' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to disconnect Gmail')
  }
  return await res.json()
}

export async function fetchUserData() {
  try {
    const res = await fetch('/api/user/data')
    if (!res.ok) return { tasks: [], workspaces: [], approvals: [], activity: [] }
    return await res.json()
  } catch {
    return { tasks: [], workspaces: [], approvals: [], activity: [] }
  }
}

export async function createUserTask(task) {
  const res = await fetch('/api/user/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(task)
  })
  if (!res.ok) throw new Error('Failed to create task')
  return await res.json()
}

export async function toggleUserTask(taskId) {
  const res = await fetch(`/api/user/tasks/${taskId}/toggle`, { method: 'POST' })
  if (!res.ok) throw new Error('Failed to update task')
  return await res.json()
}

export async function createUserWorkspace(ws) {
  const res = await fetch('/api/user/workspaces', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(ws)
  })
  if (!res.ok) throw new Error('Failed to create workspace')
  return await res.json()
}

export async function handleApprovalActionApi(approvalId, action) {
  const res = await fetch(`/api/user/approvals/${approvalId}/action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action })
  })
  if (!res.ok) throw new Error('Failed to process approval action')
  return await res.json()
}
