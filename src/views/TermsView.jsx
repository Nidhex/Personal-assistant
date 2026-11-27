import React from 'react'
import { FileText, ArrowLeft, ShieldAlert, Cpu, CheckCircle2, AlertTriangle, Scale } from 'lucide-react'

export default function TermsView({ onNavigate }) {
  return (
    <div className="min-h-screen bg-[#F7F4EB] text-[#242424] p-4 sm:p-6 lg:p-12">
      <div className="max-w-4xl mx-auto space-y-8">
        {/* Navigation Bar */}
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={() => onNavigate?.('/')}
            className="inline-flex items-center gap-2 text-xs font-medium text-[#4B5563] hover:text-[#242424] bg-[#FFFDF8] border border-[#DEDAD0] px-3.5 py-2 rounded-xl transition-colors shadow-warm-sm cursor-pointer"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>Back to Application</span>
          </button>
          <div className="flex items-center gap-2 text-xs text-[#713F12]">
            <a
              href="/privacy"
              onClick={(e) => { e.preventDefault(); onNavigate?.('/privacy') }}
              className="hover:underline text-[#4B5563] hover:text-[#242424]"
            >
              Privacy Policy
            </a>
          </div>
        </div>

        {/* Header */}
        <div className="bg-[#FFFDF8] border border-[#DEDAD0] rounded-2xl p-6 sm:p-8 shadow-warm-sm space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#E9DB91]/40 border border-[#E9DB91] text-[11px] font-semibold text-[#854D0E]">
            <FileText className="h-3.5 w-3.5" />
            <span>Terms of Service</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-serif font-bold text-[#242424] tracking-tight">
            Terms of Service
          </h1>
          <p className="text-xs text-[#6B7280]">
            Last updated: November 2026 • Applies to Personal AI Assistant
          </p>
          <p className="text-xs text-[#4B5563] leading-relaxed">
            Please read these Terms of Service (&quot;Terms&quot;) carefully before using the Personal AI Assistant web application (&quot;Application&quot;, &quot;Service&quot;). By accessing or using the Application, you agree to be bound by these Terms. If you do not agree to these Terms, do not use the Application.
          </p>
        </div>

        {/* Content Sections */}
        <div className="space-y-6">
          {/* Section 1 */}
          <div className="bg-[#FFFDF8] border border-[#DEDAD0] rounded-2xl p-6 shadow-warm-sm space-y-3">
            <div className="flex items-center gap-2.5 text-sm font-semibold text-[#242424]">
              <CheckCircle2 className="h-4 w-4 text-[#854D0E]" />
              <h2>1. Description of Application Services</h2>
            </div>
            <p className="text-xs text-[#4B5563] leading-relaxed">
              Personal AI Assistant is an interactive productivity software designed for individual personal productivity and study workflows. Core features include:
            </p>
            <ul className="text-xs text-[#4B5563] space-y-1.5 list-disc pl-5">
              <li><strong>Task Management:</strong> Creating, prioritizing, editing, and completing personal tasks.</li>
              <li><strong>Calendar Conflict Auditing:</strong> Organizing calendar events and auditing conflicting schedules.</li>
              <li><strong>Study Workspaces:</strong> Organizing study materials, revision plans, and structured notes derived from YouTube educational transcripts.</li>
              <li><strong>Supervised Email Task Proposals:</strong> Inspecting incoming Gmail messages with read-only access to propose actionable task items.</li>
              <li><strong>Daily Briefing Digests:</strong> Summarizing pending priorities and inbox activity on demand or on a scheduled basis.</li>
            </ul>
          </div>

          {/* Section 2 */}
          <div className="bg-[#FFFDF8] border border-[#DEDAD0] rounded-2xl p-6 shadow-warm-sm space-y-3">
            <div className="flex items-center gap-2.5 text-sm font-semibold text-[#242424]">
              <Cpu className="h-4 w-4 text-[#854D0E]" />
              <h2>2. AI-Generated Content &amp; Human-in-the-Loop Supervision</h2>
            </div>
            <div className="space-y-2 text-xs text-[#4B5563] leading-relaxed">
              <p><strong>Informational Purposes Only:</strong> The Application uses artificial intelligence models to assist with project planning, email summarization, and study assistance. All AI outputs, summaries, suggestions, and proposed action items are provided strictly for informational and planning purposes.</p>
              <p><strong>Mandatory User Review:</strong> You acknowledge that you are responsible for reviewing and verifying the accuracy of any task or action proposal. The Assistant does not execute destructive or irreversible external actions without explicit user approval through the Approvals review gate.</p>
              <p><strong>Emergency Kill Switch:</strong> The Application includes an emergency Kill Switch accessible from the Activity &amp; Trace and Daily Briefing views. Engaging the Kill Switch immediately halts scheduled and background agent runs.</p>
            </div>
          </div>

          {/* Section 3 */}
          <div className="bg-[#FFFDF8] border border-[#DEDAD0] rounded-2xl p-6 shadow-warm-sm space-y-3">
            <div className="flex items-center gap-2.5 text-sm font-semibold text-[#242424]">
              <ShieldAlert className="h-4 w-4 text-[#854D0E]" />
              <h2>3. User Responsibilities &amp; Acceptable Use</h2>
            </div>
            <p className="text-xs text-[#4B5563] leading-relaxed">
              When using Personal AI Assistant, you agree to:
            </p>
            <ul className="text-xs text-[#4B5563] space-y-1.5 list-disc pl-5">
              <li>Use the Application solely for lawful personal productivity purposes.</li>
              <li>Maintain the security of your Google account and credentials.</li>
              <li>Not attempt to reverse-engineer, decompile, probe, or compromise the Application infrastructure, database, or other users&apos; accounts.</li>
              <li>Not use automated scripts to abuse, rate-limit, or overload upstream APIs (including YouTube, Google APIs, and Cloudflare Workers).</li>
            </ul>
          </div>

          {/* Section 4 */}
          <div className="bg-[#FFFDF8] border border-[#DEDAD0] rounded-2xl p-6 shadow-warm-sm space-y-3">
            <div className="flex items-center gap-2.5 text-sm font-semibold text-[#242424]">
              <AlertTriangle className="h-4 w-4 text-[#854D0E]" />
              <h2>4. Service Availability &amp; As-Is Disclaimer</h2>
            </div>
            <div className="space-y-2 text-xs text-[#4B5563] leading-relaxed">
              <p>The Application is provided on an <strong>&quot;AS IS&quot;</strong> and <strong>&quot;AS AVAILABLE&quot;</strong> basis without warranties of any kind, whether express, statutory, or implied.</p>
              <p>We do not warrant that the Service will be uninterrupted, error-free, completely secure, or free of defects. Service availability is dependent upon third-party providers including Cloudflare infrastructure, Google OAuth and Gmail APIs, and YouTube caption services.</p>
              <p>We reserve the right to modify, update, suspend, or discontinue the Application or any specific feature at any time without prior notice.</p>
            </div>
          </div>

          {/* Section 5 */}
          <div className="bg-[#FFFDF8] border border-[#DEDAD0] rounded-2xl p-6 shadow-warm-sm space-y-3">
            <div className="flex items-center gap-2.5 text-sm font-semibold text-[#242424]">
              <Scale className="h-4 w-4 text-[#854D0E]" />
              <h2>5. Limitation of Liability</h2>
            </div>
            <p className="text-xs text-[#4B5563] leading-relaxed">
              To the maximum extent permitted by applicable law, the developers, contributors, and operators of Personal AI Assistant shall not be liable for any direct, indirect, incidental, consequential, special, or exemplary damages, including but not limited to loss of data, loss of business, missed deadlines, or service interruptions arising out of or in connection with your use of the Application.
            </p>
          </div>

          {/* Section 6 */}
          <div className="bg-[#FFFDF8] border border-[#DEDAD0] rounded-2xl p-6 shadow-warm-sm space-y-3">
            <div className="flex items-center gap-2.5 text-sm font-semibold text-[#242424]">
              <CheckCircle2 className="h-4 w-4 text-[#854D0E]" />
              <h2>6. Termination &amp; Disconnection</h2>
            </div>
            <p className="text-xs text-[#4B5563] leading-relaxed">
              You may terminate your agreement with these Terms at any time by signing out, disconnecting your Google account via Connected Accounts, and ceasing all use of the Application. We reserve the right to suspend or terminate access for any user who violates these Terms or engages in abusive behavior.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="text-center text-xs text-[#6B7280] pt-4 border-t border-[#DEDAD0]">
          &copy; {new Date().getFullYear()} Personal AI Assistant. All rights reserved.
        </div>
      </div>
    </div>
  )
}
