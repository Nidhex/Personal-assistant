import React from 'react'
import { ShieldCheck, ArrowLeft, Lock, Mail, Database, KeyRound, Trash2, CheckCircle2 } from 'lucide-react'

export default function PrivacyView({ onNavigate }) {
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
              href="/terms"
              onClick={(e) => { e.preventDefault(); onNavigate?.('/terms') }}
              className="hover:underline text-[#4B5563] hover:text-[#242424]"
            >
              Terms of Service
            </a>
          </div>
        </div>

        {/* Header */}
        <div className="bg-[#FFFDF8] border border-[#DEDAD0] rounded-2xl p-6 sm:p-8 shadow-warm-sm space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#E9DB91]/40 border border-[#E9DB91] text-[11px] font-semibold text-[#854D0E]">
            <ShieldCheck className="h-3.5 w-3.5" />
            <span>Official Policy Document</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-serif font-bold text-[#242424] tracking-tight">
            Privacy Policy
          </h1>
          <p className="text-xs text-[#6B7280]">
            Last updated: November 2026 • Applies to Personal AI Assistant
          </p>
          <p className="text-xs text-[#4B5563] leading-relaxed">
            Personal AI Assistant (&quot;we&quot;, &quot;our&quot;, or &quot;the Application&quot;) is a personal productivity web application designed to help individual users manage tasks, audit schedule conflicts, plan projects, organize study notes, and summarize incoming communications. We take your privacy seriously and maintain strict policies regarding user data handling.
          </p>
        </div>

        {/* Content Sections */}
        <div className="space-y-6">
          {/* Section 1 */}
          <div className="bg-[#FFFDF8] border border-[#DEDAD0] rounded-2xl p-6 shadow-warm-sm space-y-3">
            <div className="flex items-center gap-2.5 text-sm font-semibold text-[#242424]">
              <KeyRound className="h-4 w-4 text-[#854D0E]" />
              <h2>1. Google OAuth 2.0 & Identity Data Collection</h2>
            </div>
            <p className="text-xs text-[#4B5563] leading-relaxed">
              When you sign in to Personal AI Assistant using Google OAuth 2.0, we request access to basic identity scopes:
            </p>
            <ul className="text-xs text-[#4B5563] space-y-1.5 list-disc pl-5">
              <li><code className="bg-[#EFECE2] px-1 py-0.5 rounded font-mono text-[11px]">openid</code>: Unique identifier verification</li>
              <li><code className="bg-[#EFECE2] px-1 py-0.5 rounded font-mono text-[11px]">https://www.googleapis.com/auth/userinfo.email</code>: Primary email address</li>
              <li><code className="bg-[#EFECE2] px-1 py-0.5 rounded font-mono text-[11px]">https://www.googleapis.com/auth/userinfo.profile</code>: Display name and profile picture URL</li>
            </ul>
            <p className="text-xs text-[#4B5563] leading-relaxed">
              This information is used strictly to authenticate you, establish your secure session, and identify your personal workspace. We do not sell or monetize your personal information.
            </p>
          </div>

          {/* Section 2 */}
          <div className="bg-[#FFFDF8] border border-[#DEDAD0] rounded-2xl p-6 shadow-warm-sm space-y-3">
            <div className="flex items-center gap-2.5 text-sm font-semibold text-[#242424]">
              <Mail className="h-4 w-4 text-[#854D0E]" />
              <h2>2. Gmail Read-Only Access & Limited Use Disclosure</h2>
            </div>
            <p className="text-xs text-[#4B5563] leading-relaxed">
              With your explicit authorization, the Application requests the read-only Gmail scope:
            </p>
            <div className="bg-[#F7F4EB] border border-[#DEDAD0] p-3 rounded-xl font-mono text-[11px] text-[#242424]">
              https://www.googleapis.com/auth/gmail.readonly
            </div>
            <div className="space-y-2 text-xs text-[#4B5563] leading-relaxed">
              <p><strong>Purpose of Access:</strong> Gmail read-only access is used exclusively to fetch message subject lines, sender metadata, timestamps, and message snippets so you can review emails inside your personal dashboard and allow the Assistant to propose actionable task items.</p>
              <p><strong>Scope Limitations:</strong> We do NOT request permissions to compose, send, modify, forward, archive, or delete your emails. The access is strictly read-only.</p>
              <p><strong>Supervised Human-in-the-Loop Policy:</strong> The Assistant NEVER takes autonomous external actions or updates tasks without your explicit review and approval in the Approvals panel.</p>
              <p><strong>Compliance with Google Limited Use Policy:</strong> Personal AI Assistant&apos;s use and transfer to any other app of information received from Google APIs will adhere to the <a href="https://developers.google.com/terms/api-services-user-data-policy" target="_blank" rel="noopener noreferrer" className="text-[#854D0E] underline font-medium">Google API Services User Data Policy</a>, including the Limited Use requirements.</p>
              <p>We do not use Google user data to serve advertisements, train generalized third-party machine learning models, or transfer data to data brokers.</p>
            </div>
          </div>

          {/* Section 3 */}
          <div className="bg-[#FFFDF8] border border-[#DEDAD0] rounded-2xl p-6 shadow-warm-sm space-y-3">
            <div className="flex items-center gap-2.5 text-sm font-semibold text-[#242424]">
              <Database className="h-4 w-4 text-[#854D0E]" />
              <h2>3. Data Storage, Architecture & User Isolation</h2>
            </div>
            <p className="text-xs text-[#4B5563] leading-relaxed">
              All application data is stored in Cloudflare D1, a distributed serverless SQLite database hosted on Cloudflare&apos;s global network:
            </p>
            <ul className="text-xs text-[#4B5563] space-y-1.5 list-disc pl-5">
              <li><strong>Strict User Isolation:</strong> Every database table enforces foreign key constraints and user isolation predicates (<code className="bg-[#EFECE2] px-1 py-0.5 rounded font-mono text-[11px]">user_id = ?</code>). One user cannot view, modify, or delete another user&apos;s tasks, calendar events, notes, or execution logs.</li>
              <li><strong>Local Development Data:</strong> In local development mode, a local SQLite database file (<code className="bg-[#EFECE2] px-1 py-0.5 rounded font-mono text-[11px]">backend/data.db</code>) is used and never synced to public repositories.</li>
            </ul>
          </div>

          {/* Section 4 */}
          <div className="bg-[#FFFDF8] border border-[#DEDAD0] rounded-2xl p-6 shadow-warm-sm space-y-3">
            <div className="flex items-center gap-2.5 text-sm font-semibold text-[#242424]">
              <Lock className="h-4 w-4 text-[#854D0E]" />
              <h2>4. Encryption of Credentials and Sensitive Tokens</h2>
            </div>
            <p className="text-xs text-[#4B5563] leading-relaxed">
              OAuth access and refresh tokens returned by Google are encrypted at rest using <strong>Fernet symmetric cryptography</strong> (AES-128-CBC with HMAC-SHA256 authenticated encryption) before being inserted into the database:
            </p>
            <ul className="text-xs text-[#4B5563] space-y-1.5 list-disc pl-5">
              <li>Tokens are never written to database tables or logs in plaintext format.</li>
              <li>Encryption keys are stored as encrypted environment secrets on Cloudflare Workers and are never exposed in source code.</li>
              <li>Decrypted tokens exist only transiently in worker memory during the active execution of authorized user requests.</li>
            </ul>
          </div>

          {/* Section 5 */}
          <div className="bg-[#FFFDF8] border border-[#DEDAD0] rounded-2xl p-6 shadow-warm-sm space-y-3">
            <div className="flex items-center gap-2.5 text-sm font-semibold text-[#242424]">
              <Trash2 className="h-4 w-4 text-[#854D0E]" />
              <h2>5. Data Retention, Revocation & Deletion Rights</h2>
            </div>
            <div className="space-y-2 text-xs text-[#4B5563] leading-relaxed">
              <p><strong>Session Expiration:</strong> Browser session cookies are HTTP-only, secure, and configured with a 7-day lifespan. OAuth CSRF state parameters expire after 10 minutes.</p>
              <p><strong>Disconnecting Gmail:</strong> You can disconnect your Gmail account at any time directly within the application by navigating to <em>Connected Accounts &gt; Disconnect Gmail</em>. Disconnecting immediately revokes the token with Google and removes the encrypted token from our database.</p>
              <p><strong>Revoking via Google:</strong> You can independently revoke access at any time through your <a href="https://myaccount.google.com/permissions" target="_blank" rel="noopener noreferrer" className="text-[#854D0E] underline font-medium">Google Security Settings (Third-party apps with account access)</a>.</p>
              <p><strong>Account & Data Deletion Requests:</strong> If you wish to delete your user record and all associated tasks, events, and notes from our database, send a request to our administrative contact at <code className="bg-[#EFECE2] px-1 py-0.5 rounded font-mono text-[11px]">nidsvaishnav10@gmail.com</code>. Deletion requests are processed promptly.</p>
            </div>
          </div>

          {/* Section 6 */}
          <div className="bg-[#FFFDF8] border border-[#DEDAD0] rounded-2xl p-6 shadow-warm-sm space-y-3">
            <div className="flex items-center gap-2.5 text-sm font-semibold text-[#242424]">
              <CheckCircle2 className="h-4 w-4 text-[#854D0E]" />
              <h2>6. Contact Information</h2>
            </div>
            <p className="text-xs text-[#4B5563] leading-relaxed">
              For privacy-related inquiries, data requests, or questions regarding our Google OAuth integration, please contact:
            </p>
            <div className="bg-[#F7F4EB] border border-[#DEDAD0] p-3 rounded-xl text-xs space-y-1 font-mono text-[#242424]">
              <div><strong>Application:</strong> Personal AI Assistant</div>
              <div><strong>Administrator:</strong> Nidhish Vaishnav</div>
              <div><strong>Email:</strong> nidsvaishnav10@gmail.com</div>
              <div><strong>Deployment:</strong> Cloudflare Workers &amp; Pages</div>
            </div>
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
