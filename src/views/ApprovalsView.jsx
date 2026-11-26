import React from 'react'
import {
  ShieldAlert,
  CheckCircle2,
  XCircle,
  Lock
} from 'lucide-react'
import { handleApprovalActionApi } from '../api'

export default function ApprovalsView({
  approvals = [],
  onApprovalsChanged,
  showToast
}) {
  const handleApprove = async (id) => {
    try {
      await handleApprovalActionApi(id, 'approve')
      showToast('Item approved and signed off.')
      if (onApprovalsChanged) onApprovalsChanged()
    } catch {
      showToast('Failed to approve item.')
    }
  }

  const handleReject = async (id) => {
    try {
      await handleApprovalActionApi(id, 'reject')
      showToast('Item rejected: action was blocked.')
      if (onApprovalsChanged) onApprovalsChanged()
    } catch {
      showToast('Failed to reject item.')
    }
  }

  return (
    <div className="space-y-6">
      {/* Policy Guardrail Header Banner */}
      <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 rounded-lg bg-[#EBC1D9]/50 border border-[#EBC1D9] p-2 text-[#171717]">
            <ShieldAlert className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-[#242424]">Human Approval Review Workspace</h2>
            <p className="text-xs text-[#6B7280] mt-0.5">
              Outbound emails, calendar shifts, and external updates require explicit authorization.
              <strong> Sending remains disabled without human sign-off.</strong>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs font-mono text-[#242424] bg-[#F7F4EB] border border-[#DEDAD0] px-3 py-1.5 rounded-xl shrink-0">
          <Lock className="h-3.5 w-3.5 text-[#6B7280]" />
          <span>No Unsupervised Egress</span>
        </div>
      </div>

      {/* Approvals Queue */}
      {approvals.length === 0 ? (
        <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-12 text-center space-y-2 shadow-warm-sm">
          <CheckCircle2 className="mx-auto h-8 w-8 text-[#708A4E]" />
          <h3 className="text-sm font-semibold text-[#242424]">All actions verified.</h3>
          <p className="text-xs text-[#6B7280] max-w-sm mx-auto">
            There are currently no proposed actions awaiting your review. New drafts or schedule actions will appear here for verification.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {approvals.map((item) => (
            <div
              key={item.id}
              className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-6 space-y-4 shadow-warm-sm"
            >
              {/* Card Header */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#DEDAD0] pb-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="rounded bg-[#EBC1D9]/50 border border-[#EBC1D9] px-2 py-0.5 text-[11px] font-semibold text-[#171717]">
                    {item.type}
                  </span>
                  <span className="text-xs text-[#6B7280] font-mono">
                    Target: {item.target}
                  </span>
                </div>

                <span className="text-[11px] font-mono text-[#854D0E] rounded bg-[#E9DB91]/50 border border-[#E9DB91] px-2 py-0.5 self-start sm:self-auto">
                  Impact: {item.risk_level || 'Normal'}
                </span>
              </div>

              {/* Subject & Reason */}
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-[#242424]">{item.subject}</h3>
                <div className="text-xs text-[#4B5563] bg-[#F7F4EB] border border-[#DEDAD0] rounded-xl p-3">
                  <span className="font-semibold text-[#242424]">Authorization Reason: </span>
                  {item.reason}
                </div>
              </div>

              {/* Draft Content Preview */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs text-[#6B7280]">
                  <span className="font-medium text-[#242424]">Draft Content (Preview):</span>
                </div>

                <pre className="rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-4 text-xs text-[#242424] font-mono whitespace-pre-wrap leading-relaxed overflow-x-auto">
                  {item.draft_content}
                </pre>
              </div>

              {/* Actions Toolbar */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-t border-[#DEDAD0] pt-3 text-xs">
                <div className="text-[11px] text-[#6B7280]">
                  Decisions are permanently logged in the audit trace log.
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleReject(item.id)}
                    className="rounded-xl border border-[#EBC1D9] bg-[#EBC1D9]/30 px-3.5 py-2 font-semibold text-[#171717] hover:bg-[#EBC1D9]/60 transition-colors flex items-center gap-1.5 cursor-pointer"
                  >
                    <XCircle className="h-3.5 w-3.5" />
                    <span>Reject Action</span>
                  </button>

                  <button
                    onClick={() => handleApprove(item.id)}
                    className="rounded-xl border border-[#D5E0BD] bg-[#D5E0BD] px-4 py-2 font-semibold text-[#171717] hover:bg-[#C8D6AE] transition-colors flex items-center gap-1.5 shadow-warm-sm cursor-pointer"
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    <span>Approve & Sign Off</span>
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
