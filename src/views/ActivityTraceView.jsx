import React, { useState } from 'react'
import {
  FileText,
  Power,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ChevronDown,
  ChevronUp,
  Activity
} from 'lucide-react'

export default function ActivityTraceView({
  traces = [],
  dailyDigest = null,
  killSwitchActive,
  setKillSwitchActive,
  showToast
}) {
  const [expandedTraceId, setExpandedTraceId] = useState(null)

  const toggleExpand = (id) => {
    setExpandedTraceId(prev => (prev === id ? null : id))
  }

  return (
    <div className="space-y-6">
      {/* Kill Switch & Engine Supervision Header */}
      <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-start gap-3.5">
          <div
            className={`mt-0.5 rounded-xl p-2.5 ${
              killSwitchActive ? 'bg-[#EBC1D9] text-[#171717]' : 'bg-[#D5E0BD] text-[#171717]'
            }`}
          >
            <Power className="h-5 w-5" />
          </div>

          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-[#242424]">
                {killSwitchActive ? 'Agent Engine: EMERGENCY STOPPED' : 'Supervisory Engine: Active & Auditing'}
              </h2>
              <span
                className={`rounded px-2 py-0.5 text-[10px] font-mono font-medium border ${
                  killSwitchActive
                    ? 'bg-[#EBC1D9] border-[#EBC1D9] text-[#171717]'
                    : 'bg-[#D5E0BD]/60 border-[#D5E0BD] text-[#171717]'
                }`}
              >
                {killSwitchActive ? 'Halted' : 'Online'}
              </span>
            </div>
            <p className="text-xs text-[#6B7280] mt-0.5 max-w-xl leading-relaxed">
              {killSwitchActive
                ? 'All autonomous background syncs, tool calls, and integrations have been halted.'
                : 'Background supervisor monitors all execution steps, records data sources read, and enforces policy constraints.'}
            </p>
          </div>
        </div>

        <button
          onClick={() => {
            const next = !killSwitchActive
            setKillSwitchActive(next)
            showToast(next ? 'Emergency kill switch activated. All tasks halted.' : 'Assistant engine resumed.')
          }}
          className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all shrink-0 flex items-center gap-2 cursor-pointer shadow-warm-sm ${
            killSwitchActive
              ? 'bg-[#242424] text-[#FFFDF8] hover:bg-[#383838]'
              : 'border border-[#EBC1D9] bg-[#EBC1D9]/30 text-[#171717] hover:bg-[#EBC1D9]/60'
          }`}
        >
          <Power className="h-3.5 w-3.5" />
          <span>{killSwitchActive ? 'Resume Supervisory Engine' : 'Trigger Emergency Kill Switch'}</span>
        </button>
      </div>

      {/* Daily Digest Summary Card (if available) */}
      {dailyDigest && (
        <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm space-y-4">
          <div className="flex items-center justify-between border-b border-[#DEDAD0] pb-3">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-[#242424]" />
              <h3 className="text-sm font-semibold text-[#242424]">Daily Execution Digest</h3>
            </div>
            <span className="text-xs text-[#6B7280] font-mono">{dailyDigest.date}</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
            <div className="space-y-1.5 bg-[#F7F4EB] border border-[#DEDAD0] p-4 rounded-xl">
              <div className="font-semibold text-[#242424] flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-[#708A4E]" />
                <span>Completed Work:</span>
              </div>
              <p className="text-[#6B7280] leading-relaxed font-sans">{dailyDigest.completedSummary}</p>
            </div>

            <div className="space-y-1.5 bg-[#F7F4EB] border border-[#DEDAD0] p-4 rounded-xl">
              <div className="font-semibold text-[#854D0E] flex items-center gap-1.5">
                <AlertTriangle className="h-3.5 w-3.5 text-[#854D0E]" />
                <span>Attention Items:</span>
              </div>
              <ul className="space-y-1 text-[#6B7280]">
                {dailyDigest.attentionItems?.map((item, idx) => (
                  <li key={idx} className="flex items-start gap-1.5 leading-snug">
                    <span className="text-[#854D0E]">•</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="space-y-1.5 bg-[#F7F4EB] border border-[#DEDAD0] p-4 rounded-xl">
              <div className="font-semibold text-[#991B1B] flex items-center gap-1.5">
                <XCircle className="h-3.5 w-3.5 text-[#991B1B]" />
                <span>Refused Actions (Safeguards):</span>
              </div>
              <ul className="space-y-1 text-[#6B7280]">
                {dailyDigest.refusedActions?.map((item, idx) => (
                  <li key={idx} className="flex items-start gap-1.5 leading-snug">
                    <span className="text-[#991B1B]">•</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Execution Trace Timeline & Table */}
      <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm space-y-4">
        <div className="flex items-center justify-between border-b border-[#DEDAD0] pb-3 text-xs">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-[#242424]" />
            <h3 className="font-semibold text-[#242424]">Execution Traces & Policy Decisions</h3>
          </div>
          <span className="text-[#6B7280] font-mono">Total Runs: {traces.length}</span>
        </div>

        {traces.length === 0 ? (
          <div className="py-12 text-center text-xs text-[#6B7280]">
            No assistant activity recorded yet. Execution traces will appear here when assistant tasks are run.
          </div>
        ) : (
          <div className="divide-y divide-[#DEDAD0]">
            {traces.map((trace) => {
              const isExpanded = expandedTraceId === trace.id
              const isRefused = trace.status === 'Refused' || trace.status === 'Blocked'
              return (
                <div key={trace.id} className="py-3.5 first:pt-0 last:pb-0 space-y-2">
                  <div
                    onClick={() => toggleExpand(trace.id)}
                    className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 cursor-pointer hover:bg-[#F7F4EB]/50 p-2 -mx-2 rounded-xl transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <span
                        className={`flex h-2.5 w-2.5 rounded-full ${
                          isRefused
                            ? 'bg-[#EF4444]'
                            : trace.status === 'Completed'
                            ? 'bg-[#708A4E]'
                            : 'bg-[#E9DB91]'
                        }`}
                      />
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-semibold text-[#242424]">{trace.trigger}</span>
                          <span className="text-[10px] font-mono text-[#9CA3AF]">[{trace.id}]</span>
                        </div>
                        <div className="text-[11px] text-[#6B7280]">{trace.action}</div>
                      </div>
                    </div>

                    <div className="flex items-center gap-3 self-start sm:self-auto">
                      <span
                        className={`rounded px-2 py-0.5 text-[10px] font-mono font-medium border ${
                          isRefused
                            ? 'bg-[#EBC1D9] border-[#EBC1D9] text-[#171717]'
                            : trace.status === 'Completed'
                            ? 'bg-[#D5E0BD]/50 border-[#D5E0BD] text-[#171717]'
                            : 'bg-[#E9DB91]/50 border-[#E9DB91] text-[#171717]'
                        }`}
                      >
                        {trace.status}
                      </span>
                      <span className="text-[10px] text-[#9CA3AF] font-mono">{trace.timestamp}</span>
                      {isExpanded ? (
                        <ChevronUp className="h-4 w-4 text-[#9CA3AF]" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-[#9CA3AF]" />
                      )}
                    </div>
                  </div>

                  {/* Expanded Trace Audit Details */}
                  {isExpanded && (
                    <div className="mt-2 rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-4 text-xs space-y-2.5 animate-in fade-in duration-150">
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[11px]">
                        <div>
                          <span className="text-[#6B7280] block">Sources Consulted:</span>
                          <span className="font-mono text-[#242424]">
                            {trace.sources ? trace.sources.join(', ') : 'None'}
                          </span>
                        </div>
                        <div>
                          <span className="text-[#6B7280] block">Supervisory Decision:</span>
                          <span className="font-mono text-[#242424]">{trace.policy_result || 'Allowed under policy'}</span>
                        </div>
                      </div>

                      {trace.details && (
                        <div>
                          <span className="text-[#6B7280] block text-[11px]">Audit Output:</span>
                          <pre className="mt-1 rounded-lg border border-[#DEDAD0] bg-[#FFFDF8] p-3 text-[10px] font-mono text-[#242424] whitespace-pre-wrap">
                            {typeof trace.details === 'object' ? JSON.stringify(trace.details, null, 2) : trace.details}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
