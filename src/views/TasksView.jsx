import React, { useState, useMemo } from 'react'
import {
  CheckSquare,
  Plus,
  Clock,
  CheckCircle2,
  Mail,
  ArrowUpDown,
  ChevronRight,
  X,
  FileText,
  Edit2,
  Trash2
} from 'lucide-react'
import { createUserTask, toggleUserTask, updateUserTask, deleteUserTask } from '../api'

export default function TasksView({
  tasks = [],
  onTasksChanged,
  showToast,
  setActiveTab
}) {
  const [filterTab, setFilterTab] = useState('all') // 'all' | 'today' | 'upcoming' | 'overdue' | 'completed'
  const [sortBy, setSortBy] = useState('created') // 'created' | 'priority' | 'due'
  const [selectedTask, setSelectedTask] = useState(null)

  // Creation form state
  const [isCreatingTask, setIsCreatingTask] = useState(false)
  const [title, setTitle] = useState('')
  const [dueDate, setDueDate] = useState('Today')
  const [dueTime, setDueTime] = useState('')
  const [priority, setPriority] = useState('normal')
  const [workspace, setWorkspace] = useState('General')
  const [submitting, setSubmitting] = useState(false)

  // Edit & Delete state in Task Inspector
  const [isEditing, setIsEditing] = useState(false)
  const [editTitle, setEditTitle] = useState('')
  const [editDueDate, setEditDueDate] = useState('')
  const [editPriority, setEditPriority] = useState('normal')
  const [savingEdit, setSavingEdit] = useState(false)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)

  // Duplicate task check
  const checkDuplicate = (newTitle, newSource, newDueDate, excludeId = null) => {
    const cleanTitle = newTitle.trim().toLowerCase()
    return tasks.some(t => {
      if (excludeId && t.id === excludeId) return false
      const existingTitle = (t.title || '').trim().toLowerCase()
      const sameTitle = existingTitle === cleanTitle
      const sameDue = (t.due_date || t.dueDate || '').toLowerCase() === (newDueDate || '').toLowerCase()
      return sameTitle && sameDue
    })
  }

  const startEditing = () => {
    if (!selectedTask) return
    setEditTitle(selectedTask.title || '')
    setEditDueDate(selectedTask.due_date || selectedTask.dueDate || '')
    setEditPriority((selectedTask.priority || 'normal').toLowerCase())
    setConfirmingDelete(false)
    setIsEditing(true)
  }

  const handleSaveEdit = async (e) => {
    e.preventDefault()
    if (!selectedTask || !editTitle.trim() || savingEdit) return
    const trimmedTitle = editTitle.trim()
    const trimmedDue = editDueDate.trim() || 'No due date'
    if (checkDuplicate(trimmedTitle, selectedTask.source, trimmedDue, selectedTask.id)) {
      showToast(`Duplicate prevented: A task with title "${trimmedTitle}" and due date "${trimmedDue}" already exists.`)
      return
    }
    setSavingEdit(true)
    try {
      const updated = await updateUserTask(selectedTask.id, {
        title: trimmedTitle,
        due_date: trimmedDue,
        priority: editPriority
      })
      setSelectedTask(updated)
      setIsEditing(false)
      showToast('Task updated.')
      if (onTasksChanged) onTasksChanged()
    } catch (err) {
      showToast(err.message || 'Failed to update task.')
    } finally {
      setSavingEdit(false)
    }
  }

  const handleConfirmDelete = async () => {
    if (!selectedTask || deleting) return
    setDeleting(true)
    try {
      await deleteUserTask(selectedTask.id)
      setSelectedTask(null)
      setConfirmingDelete(false)
      setIsEditing(false)
      showToast('Task deleted.')
      if (onTasksChanged) onTasksChanged()
    } catch (err) {
      showToast(err.message || 'Failed to delete task.')
    } finally {
      setDeleting(false)
    }
  }

  const handleCreateTask = async (e) => {
    e.preventDefault()
    if (!title.trim()) {
      showToast('Please enter a task title.')
      return
    }

    const fullDue = dueTime ? `${dueDate} at ${dueTime}` : dueDate

    // Duplicate prevention check
    if (checkDuplicate(title, 'User Created', fullDue)) {
      showToast(`Duplicate prevented: A task with title "${title.trim()}" and due date "${fullDue}" already exists.`)
      return
    }

    setSubmitting(true)
    try {
      await createUserTask({
        title: title.trim(),
        source: 'User Created',
        due_date: fullDue,
        priority: priority,
        workspace: workspace
      })
      setTitle('')
      setDueTime('')
      setIsCreatingTask(false)
      showToast('Task created and saved to database.')
      if (onTasksChanged) onTasksChanged()
    } catch {
      showToast('Failed to create task on backend.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleToggle = async (id) => {
    try {
      await toggleUserTask(id)
      if (onTasksChanged) onTasksChanged()
      if (selectedTask?.id === id) {
        setSelectedTask(prev => prev ? { ...prev, completed: !prev.completed } : null)
      }
    } catch {
      showToast('Failed to update task status.')
    }
  }

  // Filter logic
  const todayStr = new Date().toISOString().split('T')[0]
  const filteredTasks = useMemo(() => {
    return tasks.filter(t => {
      if (filterTab === 'completed') return !!t.completed
      if (filterTab === 'all') return true

      // Active filters
      if (t.completed) return false

      const due = (t.due_date || t.dueDate || '').toLowerCase()
      if (filterTab === 'today') {
        return due.includes('today') || due === todayStr
      }
      if (filterTab === 'overdue') {
        return due.includes('overdue') || (due < todayStr && /^\d{4}-\d{2}-\d{2}/.test(due))
      }
      if (filterTab === 'upcoming') {
        return !due.includes('today') && !due.includes('overdue') && !(due < todayStr && /^\d{4}-\d{2}-\d{2}/.test(due))
      }

      return true
    })
  }, [tasks, filterTab, todayStr])

  // Sort logic
  const sortedTasks = useMemo(() => {
    const list = [...filteredTasks]
    if (sortBy === 'priority') {
      const rank = { high: 1, medium: 2, normal: 3 }
      return list.sort((a, b) => (rank[a.priority] || 3) - (rank[b.priority] || 3))
    }
    if (sortBy === 'due') {
      return list.sort((a, b) => (a.due_date || '').localeCompare(b.due_date || ''))
    }
    return list // default is newest (created_at DESC from API)
  }, [filteredTasks, sortBy])

  // Counts
  const counts = {
    all: tasks.length,
    today: tasks.filter(t => !t.completed && ((t.due_date || '').toLowerCase().includes('today') || t.due_date === todayStr)).length,
    upcoming: tasks.filter(t => !t.completed && !(t.due_date || '').toLowerCase().includes('today')).length,
    overdue: tasks.filter(t => !t.completed && (t.due_date || '').toLowerCase().includes('overdue')).length,
    completed: tasks.filter(t => !!t.completed).length
  }

  return (
    <div className="space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#DEDAD0] pb-4">
        <div>
          <h2 className="text-base font-semibold text-[#242424]">Task Workspace</h2>
          <p className="text-xs text-[#6B7280] mt-0.5">
            Action items linked to emails, calendar schedules, and revision plans.
          </p>
        </div>

        <button
          onClick={() => setIsCreatingTask(true)}
          className="inline-flex items-center gap-1.5 rounded-xl bg-[#242424] px-4 py-2 text-xs font-semibold text-[#FFFDF8] hover:bg-[#383838] transition-colors cursor-pointer shadow-warm-sm self-start sm:self-auto"
        >
          <Plus className="h-3.5 w-3.5" />
          <span>New Task</span>
        </button>
      </div>

      {/* Filter Tabs & Sort Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        {/* Tab Filters */}
        <div className="flex items-center gap-1 overflow-x-auto rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] p-1 text-xs shadow-warm-sm">
          <button
            onClick={() => setFilterTab('all')}
            className={`rounded-lg px-3 py-1 font-medium transition-colors cursor-pointer shrink-0 ${
              filterTab === 'all' ? 'bg-[#242424] text-[#FFFDF8]' : 'text-[#6B7280] hover:text-[#242424]'
            }`}
          >
            All ({counts.all})
          </button>
          <button
            onClick={() => setFilterTab('today')}
            className={`rounded-lg px-3 py-1 font-medium transition-colors cursor-pointer shrink-0 ${
              filterTab === 'today' ? 'bg-[#242424] text-[#FFFDF8]' : 'text-[#6B7280] hover:text-[#242424]'
            }`}
          >
            Today ({counts.today})
          </button>
          <button
            onClick={() => setFilterTab('upcoming')}
            className={`rounded-lg px-3 py-1 font-medium transition-colors cursor-pointer shrink-0 ${
              filterTab === 'upcoming' ? 'bg-[#242424] text-[#FFFDF8]' : 'text-[#6B7280] hover:text-[#242424]'
            }`}
          >
            Upcoming ({counts.upcoming})
          </button>
          <button
            onClick={() => setFilterTab('overdue')}
            className={`rounded-lg px-3 py-1 font-medium transition-colors cursor-pointer shrink-0 ${
              filterTab === 'overdue' ? 'bg-[#242424] text-[#FFFDF8]' : 'text-[#6B7280] hover:text-[#242424]'
            }`}
          >
            Overdue ({counts.overdue})
          </button>
          <button
            onClick={() => setFilterTab('completed')}
            className={`rounded-lg px-3 py-1 font-medium transition-colors cursor-pointer shrink-0 ${
              filterTab === 'completed' ? 'bg-[#242424] text-[#FFFDF8]' : 'text-[#6B7280] hover:text-[#242424]'
            }`}
          >
            Completed ({counts.completed})
          </button>
        </div>

        {/* Sort Selector */}
        <div className="flex items-center gap-2 text-xs text-[#6B7280]">
          <span className="flex items-center gap-1">
            <ArrowUpDown className="h-3 w-3" />
            Sort by:
          </span>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="rounded-lg border border-[#DEDAD0] bg-[#FFFDF8] px-2 py-1 text-xs text-[#242424] focus:outline-none"
          >
            <option value="created">Recently Added</option>
            <option value="priority">Priority</option>
            <option value="due">Due Date</option>
          </select>
        </div>
      </div>

      {/* Main Split Layout: Tasks List + Task Details Inspector */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Tasks Table / List (7 of 12 columns) */}
        <div className="lg:col-span-7 rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm space-y-3">
          <div className="flex items-center justify-between border-b border-[#DEDAD0] pb-2 text-xs">
            <span className="font-semibold text-[#242424]">Task Items</span>
            <span className="font-mono text-[11px] text-[#6B7280]">
              {sortedTasks.length} shown
            </span>
          </div>

          {sortedTasks.length === 0 ? (
            <div className="py-14 text-center text-xs text-[#6B7280] space-y-2">
              <CheckSquare className="mx-auto h-7 w-7 text-[#9CA3AF]" />
              <p className="font-medium text-[#242424]">No tasks match this filter</p>
              <p className="text-[11px] text-[#9CA3AF]">
                {filterTab === 'completed'
                  ? 'Completed tasks will be recorded here.'
                  : 'Click "New Task" above or extract tasks from incoming emails.'}
              </p>
            </div>
          ) : (
            <div className="divide-y divide-[#DEDAD0]">
              {sortedTasks.map((task) => {
                const isSelected = selectedTask?.id === task.id
                return (
                  <div
                    key={task.id}
                    onClick={() => {
                      setSelectedTask(task)
                      setIsEditing(false)
                      setConfirmingDelete(false)
                    }}
                    className={`py-3 flex items-start gap-3 transition-colors cursor-pointer px-2.5 -mx-2.5 rounded-xl ${
                      isSelected
                        ? 'bg-[#F7F4EB] border-l-2 border-l-[#242424]'
                        : 'hover:bg-[#F7F4EB]/50'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={!!task.completed}
                      onChange={(e) => {
                        e.stopPropagation()
                        handleToggle(task.id)
                      }}
                      className="mt-0.5 h-4 w-4 rounded border-[#DEDAD0] text-[#242424] accent-[#242424] cursor-pointer"
                    />

                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-2">
                        <span
                          className={`text-xs ${
                            task.completed
                              ? 'line-through text-[#9CA3AF]'
                              : 'font-medium text-[#242424]'
                          }`}
                        >
                          {task.title}
                        </span>

                        {task.priority === 'high' && (
                          <span className="rounded bg-[#EBC1D9]/60 border border-[#EBC1D9] px-1.5 py-0.2 text-[9px] font-semibold text-[#171717] shrink-0">
                            High Priority
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-3 mt-1 text-[11px] text-[#6B7280]">
                        <span className="font-mono text-[#242424] flex items-center gap-1">
                          <Clock className="h-3 w-3 text-[#9CA3AF]" />
                          {task.due_date || task.dueDate || 'No due date'}
                        </span>

                        {task.source && (
                          <span className="truncate max-w-[150px] text-[#9CA3AF]">
                            • {task.source}
                          </span>
                        )}

                        {task.workspace && (
                          <span className="rounded bg-[#F7F4EB] px-1.5 py-0.2 text-[9px] text-[#6B7280]">
                            {task.workspace}
                          </span>
                        )}
                      </div>
                    </div>

                    <ChevronRight className="h-4 w-4 text-[#9CA3AF] self-center shrink-0" />
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Right: Task Details Inspector (5 of 12 columns) */}
        <div className="lg:col-span-5 rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-[#DEDAD0] pb-3 text-xs">
              <span className="font-semibold text-[#242424]">Task Inspector</span>
              {selectedTask && (
                <button
                  onClick={() => setSelectedTask(null)}
                  className="text-xs text-[#6B7280] hover:text-[#242424]"
                >
                  Clear
                </button>
              )}
            </div>

            {selectedTask ? (
              <div className="mt-4 space-y-4 text-xs">
                <div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`rounded px-2 py-0.5 text-[10px] font-mono font-medium border ${
                        selectedTask.completed
                          ? 'bg-[#D5E0BD]/50 border-[#D5E0BD] text-[#171717]'
                          : 'bg-[#E9DB91]/50 border-[#E9DB91] text-[#171717]'
                      }`}
                    >
                      {selectedTask.completed ? 'Status: Completed' : 'Status: In Progress'}
                    </span>
                    <span className="font-mono text-[10px] text-[#9CA3AF]">
                      ID: {selectedTask.id}
                    </span>
                  </div>

                  <h3 className="text-sm font-semibold text-[#242424] mt-2">
                    {selectedTask.title}
                  </h3>
                </div>

                {isEditing ? (
                  <form onSubmit={handleSaveEdit} className="rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-3.5 space-y-3 text-[11px]">
                    <div>
                      <label className="block text-[#6B7280] mb-1 font-medium">Title</label>
                      <input
                        type="text"
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        maxLength={200}
                        className="w-full rounded-lg border border-[#DEDAD0] bg-[#FFFDF8] px-2.5 py-1.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
                        placeholder="Task title"
                      />
                    </div>
                    <div>
                      <label className="block text-[#6B7280] mb-1 font-medium">Due Date</label>
                      <input
                        type="text"
                        value={editDueDate}
                        onChange={(e) => setEditDueDate(e.target.value)}
                        className="w-full rounded-lg border border-[#DEDAD0] bg-[#FFFDF8] px-2.5 py-1.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
                        placeholder="e.g. Today, Tomorrow, Friday"
                      />
                    </div>
                    <div>
                      <label className="block text-[#6B7280] mb-1 font-medium">Priority</label>
                      <select
                        value={editPriority}
                        onChange={(e) => setEditPriority(e.target.value)}
                        className="w-full rounded-lg border border-[#DEDAD0] bg-[#FFFDF8] px-2.5 py-1.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
                      >
                        <option value="normal">Normal</option>
                        <option value="medium">Medium</option>
                        <option value="high">High</option>
                      </select>
                    </div>
                    <div className="flex gap-2 pt-1">
                      <button
                        type="submit"
                        disabled={!editTitle.trim() || savingEdit}
                        className="flex-1 rounded-lg bg-[#242424] py-1.5 text-xs font-semibold text-[#FFFDF8] hover:bg-[#383838] disabled:opacity-50 transition-colors cursor-pointer"
                      >
                        {savingEdit ? 'Saving...' : 'Save'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setIsEditing(false)}
                        disabled={savingEdit}
                        className="flex-1 rounded-lg border border-[#DEDAD0] bg-[#FFFDF8] py-1.5 text-xs font-semibold text-[#242424] hover:bg-[#EFECE2] transition-colors cursor-pointer"
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                ) : (
                <div className="rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-3.5 space-y-2 text-[11px]">
                  <div className="flex items-center justify-between">
                    <span className="text-[#6B7280]">Due Deadline:</span>
                    <span className="font-mono font-medium text-[#242424]">
                      {selectedTask.due_date || selectedTask.dueDate || 'None'}
                    </span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-[#6B7280]">Priority Level:</span>
                    <span className="capitalize font-medium text-[#242424]">
                      {selectedTask.priority || 'Normal'}
                    </span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-[#6B7280]">Workspace Context:</span>
                    <span className="text-[#242424]">
                      {selectedTask.workspace || 'General'}
                    </span>
                  </div>

                  <div className="flex items-start justify-between gap-2 pt-1 border-t border-[#DEDAD0]">
                    <span className="text-[#6B7280]">Source Reference:</span>
                    <span className="text-[#242424] text-right break-words max-w-[180px]">
                      {selectedTask.source || 'Manual User Creation'}
                    </span>
                  </div>
                </div>
                )}

                {/* Source Navigation Links */}
                {selectedTask.source_email_id && (
                  <div className="rounded-xl border border-[#B9CDE7] bg-[#B9CDE7]/20 p-3 space-y-2">
                    <div className="flex items-center gap-1.5 font-semibold text-[#171717] text-[11px]">
                      <Mail className="h-3.5 w-3.5" />
                      <span>Extracted from Email</span>
                    </div>
                    <button
                      onClick={() => setActiveTab && setActiveTab('inbox')}
                      className="w-full rounded-lg bg-[#242424] py-1.5 text-[11px] font-semibold text-[#FFFDF8] hover:bg-[#383838] transition-colors"
                    >
                      View Source Email in Inbox
                    </button>
                  </div>
                )}

                {/* Status Toggle & Edit/Delete Actions */}
                <div className="pt-2 space-y-2">
                  <button
                    onClick={() => handleToggle(selectedTask.id)}
                    className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] py-2 text-xs font-semibold text-[#242424] hover:bg-[#EFECE2] transition-colors cursor-pointer"
                  >
                    {selectedTask.completed ? 'Reopen Task' : 'Mark as Completed'}
                  </button>

                  {!isEditing && !confirmingDelete && (
                    <div className="flex gap-2">
                      <button
                        onClick={startEditing}
                        className="flex-1 rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] py-2 text-xs font-semibold text-[#242424] hover:bg-[#F7F4EB] transition-colors cursor-pointer"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => setConfirmingDelete(true)}
                        className="flex-1 rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] py-2 text-xs font-semibold text-[#242424] hover:bg-[#F7F4EB] transition-colors cursor-pointer"
                      >
                        Delete
                      </button>
                    </div>
                  )}

                  {confirmingDelete && (
                    <div className="rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-3 space-y-2">
                      <p className="text-[11px] font-medium text-[#242424]">
                        Delete this task? This cannot be undone.
                      </p>
                      <div className="flex gap-2">
                        <button
                          onClick={() => setConfirmingDelete(false)}
                          disabled={deleting}
                          className="flex-1 rounded-lg border border-[#DEDAD0] bg-[#FFFDF8] py-1.5 text-xs font-semibold text-[#242424] hover:bg-[#EFECE2] transition-colors cursor-pointer"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={handleConfirmDelete}
                          disabled={deleting}
                          className="flex-1 rounded-lg bg-[#242424] py-1.5 text-xs font-semibold text-[#FFFDF8] hover:bg-[#383838] disabled:opacity-50 transition-colors cursor-pointer"
                        >
                          {deleting ? 'Deleting...' : 'Delete'}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="py-20 text-center text-xs text-[#6B7280] space-y-1">
                <FileText className="mx-auto h-6 w-6 text-[#9CA3AF]" />
                <p>Select any task on the left to inspect its full metadata.</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Create Task Modal */}
      {isCreatingTask && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#171717]/40 backdrop-blur-xs p-4">
          <div className="w-full max-w-lg rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-6 shadow-warm-md space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-[#DEDAD0] pb-3">
              <h3 className="text-sm font-semibold text-[#242424]">Create Action Task</h3>
              <button
                onClick={() => setIsCreatingTask(false)}
                className="text-xs text-[#6B7280] hover:text-[#242424]"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleCreateTask} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-[#242424]">Task Title</label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Review Dr. Keller's feedback on Section 3"
                  className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-[#242424]">Due Date</label>
                  <input
                    type="text"
                    value={dueDate}
                    onChange={(e) => setDueDate(e.target.value)}
                    placeholder="e.g. Today, Tomorrow, or 2026-11-28"
                    className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-[#242424]">Due Time (Optional)</label>
                  <input
                    type="time"
                    value={dueTime}
                    onChange={(e) => setDueTime(e.target.value)}
                    className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424] font-mono"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-[#242424]">Priority</label>
                  <select
                    value={priority}
                    onChange={(e) => setPriority(e.target.value)}
                    className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
                  >
                    <option value="normal">Normal</option>
                    <option value="medium">Medium</option>
                    <option value="high">High Priority</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-[#242424]">Workspace Context</label>
                  <input
                    type="text"
                    value={workspace}
                    onChange={(e) => setWorkspace(e.target.value)}
                    className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-[#DEDAD0]">
                <button
                  type="button"
                  onClick={() => setIsCreatingTask(false)}
                  className="rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] px-3.5 py-2 text-xs font-medium text-[#6B7280] hover:text-[#242424]"
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  disabled={submitting || !title.trim()}
                  className="rounded-xl bg-[#242424] px-4 py-2 text-xs font-semibold text-[#FFFDF8] hover:bg-[#383838] transition-colors disabled:opacity-30 cursor-pointer shadow-warm-sm"
                >
                  {submitting ? 'Saving...' : 'Save Task to Database'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Task Modal */}
      {isEditingTask && selectedTask && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#171717]/40 backdrop-blur-xs p-4">
          <div className="w-full max-w-lg rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-6 shadow-warm-md space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-[#DEDAD0] pb-3">
              <h3 className="text-sm font-semibold text-[#242424]">Edit Task</h3>
              <button
                onClick={() => setIsEditingTask(false)}
                className="text-xs text-[#6B7280] hover:text-[#242424]"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleUpdateTask} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-[#242424]">Task Title</label>
                <input
                  type="text"
                  required
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-[#242424]">Due Deadline</label>
                  <input
                    type="text"
                    value={editDueDate}
                    onChange={(e) => setEditDueDate(e.target.value)}
                    className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-[#242424]">Priority</label>
                  <select
                    value={editPriority}
                    onChange={(e) => setEditPriority(e.target.value)}
                    className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
                  >
                    <option value="normal">Normal</option>
                    <option value="medium">Medium</option>
                    <option value="high">High Priority</option>
                  </select>
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-[#242424]">Workspace Context</label>
                <input
                  type="text"
                  value={editWorkspace}
                  onChange={(e) => setEditWorkspace(e.target.value)}
                  className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-[#DEDAD0]">
                <button
                  type="button"
                  onClick={() => setIsEditingTask(false)}
                  className="rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] px-3.5 py-2 text-xs font-medium text-[#6B7280] hover:text-[#242424]"
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  disabled={updating || !editTitle.trim()}
                  className="rounded-xl bg-[#242424] px-4 py-2 text-xs font-semibold text-[#FFFDF8] hover:bg-[#383838] transition-colors disabled:opacity-30 cursor-pointer shadow-warm-sm"
                >
                  {updating ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
