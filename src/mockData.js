// Deprecated: All components now use live backend API & SQLite database endpoints.
// This file is retained with clean fallback stubs to prevent any dangling imports.

export const EMPTY_USER = null
export const INITIAL_EMPTY_DATA = {
  emails: [],
  tasks: [],
  calendarEvents: [],
  approvals: [],
  workspaces: [],
  activities: [],
  connectedAccounts: []
}
export const STUDY_EMPTY_DATA = {
  youtubeSample: null,
  examHelp: {
    topics: [],
    sampleQuestions: []
  }
}

export default {
  EMPTY_USER,
  INITIAL_EMPTY_DATA,
  STUDY_EMPTY_DATA
}
