import React, { useState } from 'react'
import {
  AlertTriangle,
  ListTodo,
  Clock
} from 'lucide-react'
import { createUserTask } from '../api'

const DEFAULT_PLAN = {
  goal: 'Prepare & Submit Revised Systems Architecture Paper (Section 3)',
  targetDate: 'Nov 28, 2026',
  steps: [
    {
      id: 1,
      title: 'Generate high-DPI benchmark plots with 95% error bars',
      milestone: 'Day 1: Analysis',
      date: 'Today, Nov 27',
      status: 'In Progress',
      createsTask: true
    },
    {
      id: 2,
      title: 'Incorporate co-author comments from Dr. Keller’s lab email',
      milestone: 'Day 1: Writing',
      date: 'Today, Nov 27',
      status: 'Pending',
      createsTask: true
    },
    {
      id: 3,
      title: 'Run final LaTeX compile & verify camera-ready PDF compliance',
      milestone: 'Day 2: Finalization',
      date: 'Nov 28, 02:00 PM',
      status: 'Scheduled',
      createsTask: true
    },
    {
      id: 4,
      title: 'Submit finalized submission before camera-ready cutoff (5:00 PM EST)',
      milestone: 'Day 2: Submission',
      date: 'Nov 28, 04:30 PM',
      status: 'Scheduled',
      createsTask: true
    }
  ],
  conflictDetected: 'Potential overlap with Technical Steering Committee sync scheduled on calendar.'
}

export default function PlanningView({
  showToast,
  setActiveTab
}) {
  const [goal, setGoal] = useState(DEFAULT_PLAN.goal)
  const [targetDate, setTargetDate] = useState(DEFAULT_PLAN.targetDate)
  const [currentPlan, setCurrentPlan] = useState(DEFAULT_PLAN)

  const handleGeneratePlan = (e) => {
    e.preventDefault()
    if (!goal.trim()) return

    setCurrentPlan({
      goal: goal.trim(),
      targetDate: targetDate,
      steps: [
        {
          id: 1,
          title: `Initial scope & dependency analysis for "${goal.substring(0, 32)}..."`,
          milestone: 'Phase 1: Setup',
          date: 'Day 1',
          status: 'Pending',
          createsTask: true
        },
        {
          id: 2,
          title: 'Draft execution deliverable and identify review checkpoints',
          milestone: 'Phase 2: Execution',
          date: 'Midpoint',
          status: 'Scheduled',
          createsTask: true
        },
        {
          id: 3,
          title: `Final delivery & review before ${targetDate}`,
          milestone: 'Phase 3: Delivery',
          date: targetDate,
          status: 'Scheduled',
          createsTask: true
        }
      ],
      conflictDetected: null
    })
    showToast('Plan trajectory and milestones synthesized.')
  }

  const handleConvertPlanToTasks = async () => {
    let createdCount = 0
    for (let idx = 0; idx < currentPlan.steps.length; idx++) {
      const s = currentPlan.steps[idx]
      try {
        await createUserTask({
          title: s.title,
          source: `Plan: ${currentPlan.goal.substring(0, 25)}...`,
          due_date: s.date,
          priority: idx === 0 ? 'high' : 'medium',
          workspace: 'Planning'
        })
        createdCount++
      } catch {
        // continue
      }
    }
    showToast(`Converted ${createdCount} plan steps into active database tasks.`)
    setActiveTab('tasks')
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="border-b border-[#DEDAD0] pb-4">
        <h2 className="text-base font-semibold text-[#242424]">Project & Milestone Planning</h2>
        <p className="text-xs text-[#6B7280] mt-0.5">
          Formulate multi-step project trajectories, audit potential calendar overlaps, and instantiate actionable tasks.
        </p>
      </div>

      {/* Goal Formulation Form */}
      <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm space-y-4">
        <form onSubmit={handleGeneratePlan} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="md:col-span-2 space-y-1.5">
              <label className="text-xs font-semibold text-[#242424]">Project Goal / Target Deliverable</label>
              <input
                type="text"
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder="e.g. Prepare and submit camera-ready paper for Section 3..."
                className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] px-3.5 py-2.5 text-xs text-[#242424] placeholder:text-[#9CA3AF] focus:border-[#242424] focus:bg-[#FFFDF8] focus:outline-none transition-all"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-[#242424]">Target Date / Deadline</label>
              <input
                type="text"
                value={targetDate}
                onChange={(e) => setTargetDate(e.target.value)}
                className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] px-3.5 py-2.5 text-xs text-[#242424] focus:border-[#242424] focus:bg-[#FFFDF8] focus:outline-none transition-all font-mono"
              />
            </div>
          </div>

          <div className="flex items-center justify-between pt-1">
            <span className="text-[11px] text-[#6B7280] font-mono">
              Evaluates deadlines against schedule availability
            </span>
            <button
              type="submit"
              className="rounded-xl bg-[#242424] px-4 py-2 text-xs font-semibold text-[#FFFDF8] hover:bg-[#383838] transition-colors cursor-pointer"
            >
              Generate Structured Plan
            </button>
          </div>
        </form>
      </div>

      {/* Calendar Conflict Warning Banner if conflict detected */}
      {currentPlan.conflictDetected && (
        <div className="rounded-xl border border-[#E9DB91] bg-[#FFFDF8] p-4 shadow-warm-sm flex items-start gap-3">
          <AlertTriangle className="h-4 w-4 text-[#854D0E] shrink-0 mt-0.5" />
          <div className="text-xs space-y-0.5">
            <span className="font-semibold text-[#854D0E]">Schedule Overlap Warning:</span>
            <p className="text-[#713F12]">{currentPlan.conflictDetected}</p>
          </div>
        </div>
      )}

      {/* Structured Timeline Steps */}
      <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#DEDAD0] pb-3">
          <div>
            <h3 className="text-sm font-semibold text-[#242424]">Timeline & Execution Steps</h3>
            <p className="text-xs text-[#6B7280] mt-0.5">{currentPlan.goal}</p>
          </div>

          <button
            onClick={handleConvertPlanToTasks}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#DEDAD0] bg-[#F7F4EB] px-3 py-1.5 text-xs font-semibold text-[#242424] hover:bg-[#EFECE2] hover:border-[#242424] transition-all cursor-pointer shadow-warm-sm"
          >
            <ListTodo className="h-3.5 w-3.5" />
            <span>Convert Steps to Action Tasks</span>
          </button>
        </div>

        <div className="space-y-3 pt-1">
          {currentPlan.steps.map((step, idx) => (
            <div
              key={step.id}
              className="rounded-xl border border-[#DEDAD0] bg-[#F7F4EB]/40 p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition-colors hover:bg-[#F7F4EB]"
            >
              <div className="flex items-start gap-3">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#FFFDF8] border border-[#DEDAD0] text-[11px] font-bold text-[#242424] shrink-0 font-mono">
                  {idx + 1}
                </span>
                <div>
                  <div className="text-xs font-semibold text-[#242424]">{step.title}</div>
                  <div className="flex items-center gap-3 mt-1 text-[11px] text-[#6B7280]">
                    <span className="rounded bg-[#D5E0BD]/50 border border-[#D5E0BD] px-1.5 py-0.2 text-[9px] font-medium text-[#171717]">
                      {step.milestone}
                    </span>
                    <span className="font-mono text-[#242424] flex items-center gap-1">
                      <Clock className="h-3 w-3 text-[#6B7280]" />
                      {step.date}
                    </span>
                  </div>
                </div>
              </div>

              <span
                className={`rounded px-2 py-0.5 text-[10px] font-mono font-medium self-start sm:self-auto border ${
                  step.status === 'In Progress'
                    ? 'bg-[#E9DB91]/50 border-[#E9DB91] text-[#171717]'
                    : step.status === 'Scheduled'
                    ? 'bg-[#B9CDE7]/50 border-[#B9CDE7] text-[#171717]'
                    : 'bg-[#F7F4EB] border-[#DEDAD0] text-[#6B7280]'
                }`}
              >
                {step.status}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
