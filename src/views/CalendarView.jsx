import React, { useState, useMemo } from 'react'
import { createCalendarEvent } from '../api'
import {
  Calendar as CalendarIcon,
  Clock,
  Plus,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  ArrowRight,
  Info,
  CalendarDays,
  X,
  FileText
} from 'lucide-react'

// Helper to convert time strings (e.g. "09:00", "9:00 AM", "14:30") to minutes from midnight
function parseTimeToMinutes(timeStr) {
  if (!timeStr) return 0
  const clean = timeStr.trim().toLowerCase()
  const isPM = clean.includes('pm')
  const isAM = clean.includes('am')
  const timeOnly = clean.replace(/[ap]m/g, '').trim()
  const parts = timeOnly.split(':')
  let hours = parseInt(parts[0], 10) || 0
  const minutes = parseInt(parts[1], 10) || 0

  if (isPM && hours < 12) hours += 12
  if (isAM && hours === 12) hours = 0

  return hours * 60 + minutes
}

// Format minutes from midnight to HH:MM format
function minutesToTimeString(minutes) {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  const ampm = h >= 12 ? 'PM' : 'AM'
  const displayH = h % 12 === 0 ? 12 : h % 12
  const displayM = m < 10 ? `0${m}` : m
  return `${displayH}:${displayM} ${ampm}`
}

export default function CalendarView({
  calendarEvents = [],
  setCalendarEvents,
  tasks = [],
  currentUser = null,
  showToast,
  setActiveTab
}) {
  const [viewMode, setViewMode] = useState('week') // 'month' | 'week' | 'day'
  const [currentDate, setCurrentDate] = useState(new Date())
  const [selectedDateStr, setSelectedDateStr] = useState(
    new Date().toISOString().split('T')[0]
  )

  // Event creation form state
  const [isCreatingEvent, setIsCreatingEvent] = useState(false)
  const [eventTitle, setEventTitle] = useState('')
  const [eventDate, setEventDate] = useState(selectedDateStr)
  const [eventStartTime, setEventStartTime] = useState('09:00')
  const [eventEndTime, setEventEndTime] = useState('10:00')
  const [eventCategory, setEventCategory] = useState('Work')
  const [eventDescription, setEventDescription] = useState('')
  const [conflictWarning, setConflictWarning] = useState(null)
  const [selectedEvent, setSelectedEvent] = useState(null)

  // Check Google Calendar OAuth Permission
  const userScopes = currentUser?.scopes || []
  const hasGoogleCalendarScope = userScopes.some(s =>
    s.includes('calendar') || s.includes('calendar.events')
  )

  // Combine calendarEvents and tasks with deadlines into unified calendar items
  const allCalendarItems = useMemo(() => {
    const items = [...calendarEvents]

    // Map tasks that have a date to calendar deadline blocks
    tasks.forEach(t => {
      if (t.due_date && t.due_date !== 'No due date') {
        let taskDate = selectedDateStr
        // If due_date is YYYY-MM-DD
        if (/^\d{4}-\d{2}-\d{2}$/.test(t.due_date)) {
          taskDate = t.due_date
        }

        items.push({
          id: `task-cal-${t.id}`,
          title: `[Task] ${t.title}`,
          date: taskDate,
          time: 'Due 5:00 PM',
          startTime: '17:00',
          endTime: '17:30',
          category: 'Task Deadline',
          isTask: true,
          taskId: t.id,
          completed: !!t.completed,
          source: t.source || 'Task Management',
          description: `Deadline for task: ${t.title} (${t.priority || 'normal'} priority)`
        })
      }
    })

    return items
  }, [calendarEvents, tasks, selectedDateStr])

  // Conflict detection function
  const checkOverlap = (date, startStr, endStr) => {
    const newStart = parseTimeToMinutes(startStr)
    const newEnd = parseTimeToMinutes(endStr)

    if (newEnd <= newStart) {
      return { error: 'End time must be after start time.' }
    }

    const sameDayEvents = allCalendarItems.filter(e => (e.date === date || !e.date))
    for (const evt of sameDayEvents) {
      const evtStart = evt.startTime ? parseTimeToMinutes(evt.startTime) : parseTimeToMinutes(evt.time?.split('-')[0])
      const evtEnd = evt.endTime ? parseTimeToMinutes(evt.endTime) : evtStart + 60

      if (newStart < evtEnd && newEnd > evtStart) {
        return {
          conflict: true,
          conflictingEvent: evt,
          message: `Overlap detected with "${evt.title}" (${evt.startTime || evt.time || 'scheduled time'}).`
        }
      }
    }

    return { conflict: false }
  }

  // Handle Event Creation
  const handleSaveEvent = async (e) => {
    e.preventDefault()
    if (!eventTitle.trim()) {
      showToast('Please enter an event title.')
      return
    }

    const overlapResult = checkOverlap(eventDate, eventStartTime, eventEndTime)
    if (overlapResult.error) {
      showToast(overlapResult.error)
      return
    }

    if (overlapResult.conflict && !conflictWarning) {
      // Surface conflict to user for review before proceeding
      setConflictWarning(overlapResult.message)
      showToast('Calendar conflict detected! Review before saving.')
      return
    }

    const newEvt = {
      id: `evt-${Date.now()}`,
      title: eventTitle.trim(),
      date: eventDate,
      time: `${minutesToTimeString(parseTimeToMinutes(eventStartTime))} - ${minutesToTimeString(parseTimeToMinutes(eventEndTime))}`,
      startTime: eventStartTime,
      endTime: eventEndTime,
      category: eventCategory,
      description: eventDescription.trim() || 'Scheduled calendar block',
      source: 'User Scheduled',
      hasConflict: !!conflictWarning,
      conflictDetails: conflictWarning || null
    }

    if (setCalendarEvents) {
      setCalendarEvents(prev => [...prev, newEvt])
    }

    try {
      await createCalendarEvent({
        title: eventTitle.trim(),
        event_date: eventDate,
        start_time: eventStartTime,
        end_time: eventEndTime,
        category: eventCategory,
        description: eventDescription.trim() || 'Scheduled calendar block',
        force: !!conflictWarning
      })
    } catch {
      // Retain optimistic client display
    }

    // Reset Form
    setIsCreatingEvent(false)
    setEventTitle('')
    setEventDescription('')
    setConflictWarning(null)
    showToast('Calendar event block scheduled successfully.')
  }

  // Navigation handlers
  const handlePrev = () => {
    const next = new Date(currentDate)
    if (viewMode === 'month') next.setMonth(next.getMonth() - 1)
    else if (viewMode === 'week') next.setDate(next.getDate() - 7)
    else next.setDate(next.getDate() - 1)
    setCurrentDate(next)
    setSelectedDateStr(next.toISOString().split('T')[0])
  }

  const handleNext = () => {
    const next = new Date(currentDate)
    if (viewMode === 'month') next.setMonth(next.getMonth() + 1)
    else if (viewMode === 'week') next.setDate(next.getDate() + 7)
    else next.setDate(next.getDate() + 1)
    setCurrentDate(next)
    setSelectedDateStr(next.toISOString().split('T')[0])
  }

  const handleToday = () => {
    const now = new Date()
    setCurrentDate(now)
    setSelectedDateStr(now.toISOString().split('T')[0])
  }

  // Helper for generating week days around currentDate
  const weekDays = useMemo(() => {
    const curr = new Date(currentDate)
    const day = curr.getDay()
    const diff = curr.getDate() - day + (day === 0 ? -6 : 1) // start on Monday
    const monday = new Date(curr.setDate(diff))

    const days = []
    for (let i = 0; i < 7; i++) {
      const d = new Date(monday)
      d.setDate(monday.getDate() + i)
      const dStr = d.toISOString().split('T')[0]
      const count = allCalendarItems.filter(e => e.date === dStr).length
      days.push({
        name: d.toLocaleDateString('en-US', { weekday: 'short' }),
        dateNumber: d.getDate(),
        fullDateStr: dStr,
        isToday: dStr === new Date().toISOString().split('T')[0],
        isSelected: dStr === selectedDateStr,
        eventCount: count
      })
    }
    return days
  }, [currentDate, selectedDateStr, allCalendarItems])

  // Events on selected date
  const selectedDateEvents = useMemo(() => {
    return allCalendarItems.filter(e => e.date === selectedDateStr || !e.date)
  }, [allCalendarItems, selectedDateStr])

  return (
    <div className="space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#DEDAD0] pb-4">
        <div>
          <h2 className="text-base font-semibold text-[#242424]">Calendar & Scheduling</h2>
          <p className="text-xs text-[#6B7280] mt-0.5">
            Supervised timeline, conflict detection, and deadline synchronization.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* View Mode Buttons */}
          <div className="flex items-center gap-1 rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] p-1 text-xs shadow-warm-sm">
            <button
              onClick={() => setViewMode('day')}
              className={`rounded-lg px-3 py-1 font-medium transition-colors cursor-pointer ${
                viewMode === 'day' ? 'bg-[#242424] text-[#FFFDF8]' : 'text-[#6B7280] hover:text-[#242424]'
              }`}
            >
              Day
            </button>
            <button
              onClick={() => setViewMode('week')}
              className={`rounded-lg px-3 py-1 font-medium transition-colors cursor-pointer ${
                viewMode === 'week' ? 'bg-[#242424] text-[#FFFDF8]' : 'text-[#6B7280] hover:text-[#242424]'
              }`}
            >
              Week
            </button>
            <button
              onClick={() => setViewMode('month')}
              className={`rounded-lg px-3 py-1 font-medium transition-colors cursor-pointer ${
                viewMode === 'month' ? 'bg-[#242424] text-[#FFFDF8]' : 'text-[#6B7280] hover:text-[#242424]'
              }`}
            >
              Month
            </button>
          </div>

          {/* Create Event Button */}
          <button
            onClick={() => {
              setEventDate(selectedDateStr)
              setIsCreatingEvent(true)
            }}
            className="inline-flex items-center gap-1.5 rounded-xl bg-[#242424] px-3.5 py-2 text-xs font-semibold text-[#FFFDF8] hover:bg-[#383838] transition-colors cursor-pointer shadow-warm-sm"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>Add Block</span>
          </button>
        </div>
      </div>

      {/* Google Calendar Permission Audit Status */}
      {!hasGoogleCalendarScope && (
        <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-4 shadow-warm-sm flex items-start gap-3">
          <Info className="h-4 w-4 text-[#6B7280] shrink-0 mt-0.5" />
          <div className="text-xs space-y-0.5">
            <span className="font-semibold text-[#242424]">Google Calendar Permission Status: Workspace Managed</span>
            <p className="text-[#6B7280] leading-relaxed">
              Current Google OAuth authorization is strictly limited to read-only Gmail access (<code className="font-mono text-[#242424]">gmail.readonly</code>). Google Calendar scope is not requested in this configuration. All scheduled blocks, deadline imports, and conflict detections are managed reliably within your supervised assistant workspace.
            </p>
          </div>
        </div>
      )}

      {/* Date Navigation Strip */}
      <div className="flex items-center justify-between rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] px-5 py-3 shadow-warm-sm">
        <div className="flex items-center gap-3">
          <button
            onClick={handlePrev}
            className="rounded-lg p-1 text-[#6B7280] hover:bg-[#F7F4EB] hover:text-[#242424] transition-colors cursor-pointer"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>

          <span className="text-xs font-semibold text-[#242424] font-mono">
            {currentDate.toLocaleDateString('en-US', {
              month: 'long',
              year: 'numeric'
            })}
          </span>

          <button
            onClick={handleNext}
            className="rounded-lg p-1 text-[#6B7280] hover:bg-[#F7F4EB] hover:text-[#242424] transition-colors cursor-pointer"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>

        <button
          onClick={handleToday}
          className="rounded-lg border border-[#DEDAD0] bg-[#F7F4EB] px-2.5 py-1 text-xs font-medium text-[#242424] hover:bg-[#EFECE2] transition-colors cursor-pointer"
        >
          Today
        </button>
      </div>

      {/* Week Grid / Day Selection Strip */}
      <div className="grid grid-cols-7 gap-2">
        {weekDays.map((d, i) => (
          <button
            key={i}
            onClick={() => {
              setSelectedDateStr(d.fullDateStr)
            }}
            className={`p-3 rounded-2xl border text-center transition-all cursor-pointer ${
              d.isSelected
                ? 'border-[#242424] bg-[#FFFDF8] shadow-warm'
                : 'border-[#DEDAD0] bg-[#FFFDF8]/70 hover:bg-[#FFFDF8]'
            }`}
          >
            <div className="text-[11px] font-medium text-[#6B7280]">{d.name}</div>
            <div className={`text-sm font-bold mt-1 ${d.isToday ? 'text-[#708A4E]' : 'text-[#242424]'}`}>
              {d.dateNumber}
            </div>
            {d.eventCount > 0 && (
              <div className="mt-1 flex justify-center">
                <span className="h-1.5 w-1.5 rounded-full bg-[#B9CDE7]" />
              </div>
            )}
          </button>
        ))}
      </div>

      {/* Events & Schedule for Selected Date */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Events List (7 of 12 columns) */}
        <div className="lg:col-span-7 rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm space-y-4">
          <div className="flex items-center justify-between border-b border-[#DEDAD0] pb-3 text-xs">
            <div className="flex items-center gap-2">
              <CalendarIcon className="h-4 w-4 text-[#242424]" />
              <span className="font-semibold text-[#242424]">
                Schedule for {new Date(selectedDateStr + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', weekday: 'short' })}
              </span>
            </div>
            <span className="font-mono text-[11px] text-[#6B7280]">
              {selectedDateEvents.length} Item(s)
            </span>
          </div>

          {selectedDateEvents.length === 0 ? (
            <div className="py-14 text-center text-xs text-[#6B7280] space-y-2">
              <CalendarDays className="mx-auto h-7 w-7 text-[#9CA3AF]" />
              <p className="font-medium text-[#242424]">No events or deadlines scheduled for this date</p>
              <p className="text-[11px] text-[#9CA3AF]">Click "Add Block" above to schedule a calendar block.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {selectedDateEvents.map((evt) => (
                <div
                  key={evt.id}
                  onClick={() => setSelectedEvent(evt)}
                  className={`p-4 rounded-xl border transition-all cursor-pointer ${
                    selectedEvent?.id === evt.id
                      ? 'border-[#242424] bg-[#F7F4EB]'
                      : 'border-[#DEDAD0] bg-[#FFFDF8] hover:bg-[#F7F4EB]/50'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-semibold text-[#242424]">{evt.title}</span>
                        <span className="rounded bg-[#B9CDE7]/50 border border-[#B9CDE7] px-1.5 py-0.2 text-[9px] font-medium text-[#171717]">
                          {evt.category || 'General'}
                        </span>
                        {evt.isTask && (
                          <span className="rounded bg-[#E9DB91]/50 border border-[#E9DB91] px-1.5 py-0.2 text-[9px] font-medium text-[#171717]">
                            Task Sync
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-3 mt-1.5 text-[11px] text-[#6B7280] font-mono">
                        <span className="flex items-center gap-1 text-[#242424]">
                          <Clock className="h-3 w-3 text-[#6B7280]" />
                          {evt.time || `${evt.startTime} - ${evt.endTime}`}
                        </span>
                        {evt.source && (
                          <span className="text-[#9CA3AF]">• Source: {evt.source}</span>
                        )}
                      </div>
                    </div>

                    {evt.hasConflict && (
                      <span className="rounded bg-[#E9DB91] border border-[#E9DB91] px-2 py-0.5 text-[10px] font-semibold text-[#171717] shrink-0">
                        Overlap Warning
                      </span>
                    )}
                  </div>

                  {evt.description && (
                    <p className="text-[11px] text-[#6B7280] mt-2 line-clamp-2 leading-relaxed">
                      {evt.description}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Selected Event Details Pane (5 of 12 columns) */}
        <div className="lg:col-span-5 rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-[#DEDAD0] pb-3 text-xs">
              <span className="font-semibold text-[#242424]">Event Inspector</span>
              {selectedEvent && (
                <button
                  onClick={() => setSelectedEvent(null)}
                  className="text-xs text-[#6B7280] hover:text-[#242424]"
                >
                  Clear
                </button>
              )}
            </div>

            {selectedEvent ? (
              <div className="mt-4 space-y-4 text-xs">
                <div>
                  <h3 className="text-sm font-semibold text-[#242424]">{selectedEvent.title}</h3>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="rounded bg-[#F7F4EB] border border-[#DEDAD0] px-2 py-0.5 text-[10px] font-mono text-[#6B7280]">
                      {selectedEvent.category}
                    </span>
                    <span className="font-mono text-[11px] text-[#6B7280]">
                      Date: {selectedEvent.date || selectedDateStr}
                    </span>
                  </div>
                </div>

                <div className="rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-3 space-y-2">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-[#6B7280]">Time Block:</span>
                    <span className="font-mono font-medium text-[#242424]">
                      {selectedEvent.time || `${selectedEvent.startTime} - ${selectedEvent.endTime}`}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-[#6B7280]">Source Reference:</span>
                    <span className="font-mono text-[#242424] truncate max-w-[170px]">
                      {selectedEvent.source || 'Direct Schedule'}
                    </span>
                  </div>
                </div>

                {selectedEvent.description && (
                  <div className="space-y-1">
                    <span className="text-[11px] font-semibold text-[#6B7280]">Notes & Details:</span>
                    <p className="text-xs text-[#242424] leading-relaxed bg-[#F7F4EB]/50 p-3 rounded-xl border border-[#DEDAD0]">
                      {selectedEvent.description}
                    </p>
                  </div>
                )}

                {selectedEvent.isTask && (
                  <div className="pt-2">
                    <button
                      onClick={() => setActiveTab('tasks')}
                      className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] py-2 text-xs font-semibold text-[#242424] hover:bg-[#EFECE2] flex items-center justify-center gap-1.5 transition-colors"
                    >
                      <span>Jump to Task in Workspace</span>
                      <ArrowRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="py-20 text-center text-xs text-[#6B7280] space-y-1">
                <FileText className="mx-auto h-6 w-6 text-[#9CA3AF]" />
                <p>Select any event or deadline on the left to inspect its details.</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Add Event Modal with Mandatory Conflict Check */}
      {isCreatingEvent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#171717]/40 backdrop-blur-xs p-4">
          <div className="w-full max-w-lg rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-6 shadow-warm-md space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-[#DEDAD0] pb-3">
              <h3 className="text-sm font-semibold text-[#242424]">Schedule Calendar Block</h3>
              <button
                onClick={() => {
                  setIsCreatingEvent(false)
                  setConflictWarning(null)
                }}
                className="text-xs text-[#6B7280] hover:text-[#242424]"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Conflict Warning Box (if conflict flagged) */}
            {conflictWarning && (
              <div className="rounded-xl border border-[#E9DB91] bg-[#FFFDF8] p-3 text-xs text-[#854D0E] space-y-1 shadow-warm-sm">
                <div className="flex items-center gap-1.5 font-semibold">
                  <AlertTriangle className="h-4 w-4" />
                  <span>Time Conflict Identified</span>
                </div>
                <p className="text-[11px] text-[#713F12]">{conflictWarning}</p>
                <p className="text-[10px] text-[#854D0E] italic">
                  You can adjust the time slots below, or click "Confirm & Schedule Anyway".
                </p>
              </div>
            )}

            <form onSubmit={handleSaveEvent} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-[#242424]">Event Title</label>
                <input
                  type="text"
                  required
                  value={eventTitle}
                  onChange={(e) => {
                    setEventTitle(e.target.value)
                    setConflictWarning(null)
                  }}
                  placeholder="e.g. Systems Architecture Working Session"
                  className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-[#242424]">Date</label>
                  <input
                    type="date"
                    required
                    value={eventDate}
                    onChange={(e) => {
                      setEventDate(e.target.value)
                      setConflictWarning(null)
                    }}
                    className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424] font-mono"
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-[#242424]">Start Time</label>
                  <input
                    type="time"
                    required
                    value={eventStartTime}
                    onChange={(e) => {
                      setEventStartTime(e.target.value)
                      setConflictWarning(null)
                    }}
                    className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424] font-mono"
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-[#242424]">End Time</label>
                  <input
                    type="time"
                    required
                    value={eventEndTime}
                    onChange={(e) => {
                      setEventEndTime(e.target.value)
                      setConflictWarning(null)
                    }}
                    className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424] font-mono"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-[#242424]">Category</label>
                  <select
                    value={eventCategory}
                    onChange={(e) => setEventCategory(e.target.value)}
                    className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
                  >
                    <option value="Work">Work / Project</option>
                    <option value="Study">Study & Exam Prep</option>
                    <option value="Meeting">Meeting / Review</option>
                    <option value="Deadline">Deadline Block</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-[#242424]">Notes / Details</label>
                  <input
                    type="text"
                    value={eventDescription}
                    onChange={(e) => setEventDescription(e.target.value)}
                    placeholder="Optional details..."
                    className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-2.5 text-xs text-[#242424] focus:outline-none focus:border-[#242424]"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-[#DEDAD0]">
                <button
                  type="button"
                  onClick={() => {
                    setIsCreatingEvent(false)
                    setConflictWarning(null)
                  }}
                  className="rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] px-3.5 py-2 text-xs font-medium text-[#6B7280] hover:text-[#242424]"
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  className="rounded-xl bg-[#242424] px-4 py-2 text-xs font-semibold text-[#FFFDF8] hover:bg-[#383838] transition-colors cursor-pointer shadow-warm-sm"
                >
                  {conflictWarning ? 'Confirm & Schedule Anyway' : 'Schedule Event'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
