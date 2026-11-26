import React, { useState } from 'react'
import CalendarView from './CalendarView'
import TasksView from './TasksView'

export default function CalendarTasksView({
  calendarEvents = [],
  setCalendarEvents,
  tasks = [],
  onTasksChanged,
  currentUser = null,
  showToast,
  setActiveTab,
  activeSubtab = 'calendar'
}) {
  const [subtab, setSubtab] = useState(
    activeSubtab === 'tasks_only' || activeSubtab === 'tasks' ? 'tasks' : 'calendar'
  )

  return (
    <div className="space-y-4">
      {/* Subtab Switcher */}
      <div className="flex items-center gap-1 rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] p-1 text-xs shadow-warm-sm w-fit">
        <button
          onClick={() => setSubtab('calendar')}
          className={`rounded-lg px-4 py-1.5 font-medium transition-colors cursor-pointer ${
            subtab === 'calendar'
              ? 'bg-[#242424] text-[#FFFDF8]'
              : 'text-[#6B7280] hover:text-[#242424]'
          }`}
        >
          Calendar Schedule
        </button>
        <button
          onClick={() => setSubtab('tasks')}
          className={`rounded-lg px-4 py-1.5 font-medium transition-colors cursor-pointer ${
            subtab === 'tasks'
              ? 'bg-[#242424] text-[#FFFDF8]'
              : 'text-[#6B7280] hover:text-[#242424]'
          }`}
        >
          Tasks ({tasks.filter(t => !t.completed).length})
        </button>
      </div>

      {subtab === 'calendar' ? (
        <CalendarView
          calendarEvents={calendarEvents}
          setCalendarEvents={setCalendarEvents}
          tasks={tasks}
          currentUser={currentUser}
          showToast={showToast}
          setActiveTab={setActiveTab}
        />
      ) : (
        <TasksView
          tasks={tasks}
          onTasksChanged={onTasksChanged}
          showToast={showToast}
          setActiveTab={setActiveTab}
        />
      )}
    </div>
  )
}
