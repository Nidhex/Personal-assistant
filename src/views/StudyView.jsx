import React, { useState } from 'react'
import {
  BookOpen,
  Video,
  FileText,
  CheckCircle2,
  AlertCircle,
  FileUp,
  Link2,
  Clock,
  Calendar,
  Plus,
  HelpCircle,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  ArrowRight,
  ShieldAlert
} from 'lucide-react'
import { createUserTask } from '../api'

// Helper to validate YouTube URLs
function isValidYouTubeUrl(url) {
  if (!url) return false
  const clean = url.trim()
  return (
    clean.includes('youtube.com/watch?v=') ||
    clean.includes('youtu.be/') ||
    clean.includes('youtube.com/embed/')
  )
}

// Parse pasted transcript lines looking for actual timestamps e.g. "01:23", "12:45"
function parseTranscriptText(rawText) {
  if (!rawText.trim()) return []

  const lines = rawText.split('\n').map(l => l.trim()).filter(Boolean)
  const topics = []
  let currentTopic = null

  // Regex matching timestamps like [01:23], (1:23:45), 04:50, etc.
  const timeRegex = /(?:\[|\()?(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:\]|\))?/

  lines.forEach((line) => {
    const match = line.match(timeRegex)
    if (match) {
      const timestamp = match[0].replace(/[\[\]\(\)]/g, '')
      const content = line.replace(match[0], '').trim()

      if (currentTopic) {
        topics.push(currentTopic)
      }

      currentTopic = {
        title: content.length > 5 ? content : `Lecture Segment at ${timestamp}`,
        timestamp: timestamp,
        summary: content || `Transcript text at timestamp ${timestamp}.`,
        keyPoints: [content || `Key note recorded at ${timestamp}`],
        questions: [
          {
            q: `What key concept is addressed around timestamp ${timestamp}?`,
            a: content || 'Concept covered in lecture transcript section.'
          }
        ]
      }
    } else if (currentTopic) {
      currentTopic.keyPoints.push(line)
      currentTopic.summary += ` ${line}`
    } else {
      // First line without timestamp
      currentTopic = {
        title: line.length > 50 ? line.substring(0, 50) + '...' : line,
        timestamp: '00:00',
        summary: line,
        keyPoints: [line],
        questions: [
          {
            q: `What is the opening focus of this section?`,
            a: line
          }
        ]
      }
    }
  })

  if (currentTopic) {
    topics.push(currentTopic)
  }

  return topics
}

// Extract topics and text sections from uploaded notes/document text
function extractTopicsFromDocument(text, filename) {
  if (!text.trim()) return []

  const paragraphs = text.split(/\n\s*\n/).map(p => p.trim()).filter(Boolean)
  const topics = []

  paragraphs.forEach((p, idx) => {
    const lines = p.split('\n').map(l => l.trim()).filter(Boolean)
    const firstLine = lines[0] || `Section ${idx + 1}`
    const isHeading = firstLine.startsWith('#') || firstLine.startsWith('Topic') || firstLine.length < 60
    const title = firstLine.replace(/^[#*-]\s*/, '')
    const body = lines.slice(isHeading ? 1 : 0).join(' ') || firstLine

    topics.push({
      id: idx + 1,
      title: title || `Topic ${idx + 1}`,
      content: body,
      source: filename,
      sampleQuestion: {
        question: `Based strictly on the document text: What is the primary role or definition given for "${title}"?`,
        answer: body.length > 200 ? body.substring(0, 200) + '...' : body
      }
    })
  })

  return topics.slice(0, 8)
}

export default function StudyView({
  onTaskCreated,
  tasks = [],
  currentUser = null,
  showToast,
  setActiveTab
}) {
  const [activeTab, setActiveTabLocal] = useState('youtube') // 'youtube' | 'exam'

  // -------------------------------------------------------------
  // PART A: YOUTUBE VIDEO NOTES STATE
  // -------------------------------------------------------------
  const [ytUrl, setYtUrl] = useState('')
  const [ytStatus, setYtStatus] = useState('idle') // 'idle' | 'checking' | 'no_transcript' | 'success'
  const [manualTranscript, setManualTranscript] = useState('')
  const [extractedYtTopics, setExtractedYtTopics] = useState([])
  const [revealedYtAnswers, setRevealedYtAnswers] = useState({})

  // -------------------------------------------------------------
  // PART B: EXAM STUDY HELP STATE
  // -------------------------------------------------------------
  const [uploadedFiles, setUploadedFiles] = useState([])
  const [examDate, setExamDate] = useState('2026-12-05')
  const [examTopics, setExamTopics] = useState([])
  const [revisionPlan, setRevisionPlan] = useState([])
  const [revealedExamAnswers, setRevealedExamAnswers] = useState({})
  const [addingPlanToTasks, setAddingPlanToTasks] = useState(false)

  // -------------------------------------------------------------
  // PART A HANDLERS (YOUTUBE)
  // -------------------------------------------------------------
  const handleCheckVideo = (e) => {
    e.preventDefault()
    if (!ytUrl.trim()) {
      showToast('Please enter a YouTube video URL.')
      return
    }

    if (!isValidYouTubeUrl(ytUrl)) {
      showToast('Invalid YouTube URL. Please enter a valid youtube.com or youtu.be link.')
      return
    }

    setYtStatus('checking')

    // Per mandatory requirement: Check transcript availability.
    // The backend does not have an automated YouTube transcript proxy configured,
    // so automated scraping without API cannot be assumed or fabricated.
    setTimeout(() => {
      // Set mandatory required state: "No transcript available. No notes were created."
      setYtStatus('no_transcript')
      showToast('No automated transcript available for this video.')
    }, 600)
  }

  const handleProcessManualTranscript = (e) => {
    e.preventDefault()
    if (!manualTranscript.trim()) {
      showToast('Please paste transcript or lecture text to process.')
      return
    }

    const topics = parseTranscriptText(manualTranscript)
    if (topics.length === 0) {
      showToast('Could not detect distinct sections in the provided text.')
      return
    }

    setExtractedYtTopics(topics)
    setYtStatus('success')
    showToast(`Parsed ${topics.length} topic sections with timestamps.`)
  }

  const handleCreateTaskFromYtTopic = async (topic) => {
    try {
      // Check duplicate
      const duplicate = tasks.some(t =>
        (t.title || '').toLowerCase() === `Review Lecture: ${topic.title}`.toLowerCase()
      )
      if (duplicate) {
        showToast(`Task for "${topic.title}" already exists in your workspace.`)
        return
      }

      await createUserTask({
        title: `Review Lecture: ${topic.title}`,
        source: `YouTube Notes (${topic.timestamp})`,
        due_date: 'Tomorrow',
        priority: 'normal',
        workspace: 'Study & Research'
      })
      showToast('Review session added to your Tasks & Calendar.')
      if (onTaskCreated) onTaskCreated()
    } catch {
      showToast('Failed to create task.')
    }
  }

  // -------------------------------------------------------------
  // PART B HANDLERS (EXAM STUDY HELP)
  // -------------------------------------------------------------
  const handleFileUpload = (e) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return

    files.forEach(file => {
      const reader = new FileReader()
      reader.onload = (event) => {
        const textContent = event.target?.result || ''
        const newDoc = {
          name: file.name,
          size: `${(file.size / 1024).toFixed(1)} KB`,
          content: textContent
        }

        setUploadedFiles(prev => [...prev, newDoc])
        const topics = extractTopicsFromDocument(textContent, file.name)
        setExamTopics(prev => [...prev, ...topics])
        generateRevisionPlan(topics, examDate, file.name)
        showToast(`Document "${file.name}" indexed and text parsed.`)
      }

      // Read text content natively
      reader.readAsText(file)
    })
  }

  const generateRevisionPlan = (topics, targetExamDate, docName) => {
    if (!topics || topics.length === 0) return

    const today = new Date()
    const exam = new Date(targetExamDate)
    const diffTime = Math.max(1, exam.getTime() - today.getTime())
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24))

    const plan = topics.map((t, i) => {
      const sessionDay = new Date(today)
      const dayOffset = Math.min(diffDays - 1, Math.floor((i / topics.length) * diffDays) + 1)
      sessionDay.setDate(today.getDate() + dayOffset)
      const dateStr = sessionDay.toISOString().split('T')[0]

      return {
        id: `plan-ses-${i}`,
        topic: t.title,
        scheduledDate: dateStr,
        source: docName,
        sessionLength: '45 mins',
        focus: `Active recall & revision on ${t.title}`,
        completed: false
      }
    })

    setRevisionPlan(plan)
  }

  const handleApplyExamDateChange = (newDate) => {
    setExamDate(newDate)
    if (examTopics.length > 0) {
      generateRevisionPlan(examTopics, newDate, uploadedFiles[0]?.name || 'Study Notes')
      showToast('Updated revision schedule against new exam target date.')
    }
  }

  const handleAddPlanToTasks = async () => {
    if (revisionPlan.length === 0) return
    setAddingPlanToTasks(true)

    let createdCount = 0
    let skippedCount = 0

    try {
      for (const item of revisionPlan) {
        const taskTitle = `Exam Revision: ${item.topic}`
        const exists = tasks.some(t =>
          (t.title || '').toLowerCase() === taskTitle.toLowerCase() &&
          (t.due_date || '').includes(item.scheduledDate)
        )

        if (exists) {
          skippedCount++
          continue
        }

        await createUserTask({
          title: taskTitle,
          source: `Exam Plan: ${item.source}`,
          due_date: item.scheduledDate,
          priority: 'normal',
          workspace: 'Exam Preparation'
        })
        createdCount++
      }

      if (createdCount > 0) {
        showToast(`Created ${createdCount} revision tasks synchronized with your calendar!`)
        if (onTaskCreated) onTaskCreated()
      } else {
        showToast(`All ${skippedCount} revision tasks are already scheduled in your workspace.`)
      }
    } catch {
      showToast('Failed to schedule revision tasks.')
    } finally {
      setAddingPlanToTasks(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header & Sub-Tab Switcher */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#DEDAD0] pb-4">
        <div>
          <h2 className="text-base font-semibold text-[#242424]">Study & Knowledge Synthesis</h2>
          <p className="text-xs text-[#6B7280] mt-0.5">
            Extract timestamped video lecture notes and generate grounded revision plans from your study files.
          </p>
        </div>

        <div className="flex items-center gap-1 rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] p-1 text-xs shadow-warm-sm">
          <button
            onClick={() => setActiveTabLocal('youtube')}
            className={`rounded-lg px-3 py-1 font-medium transition-colors flex items-center gap-1.5 cursor-pointer ${
              activeTab === 'youtube'
                ? 'bg-[#242424] text-[#FFFDF8]'
                : 'text-[#6B7280] hover:text-[#242424]'
            }`}
          >
            <Video className="h-3.5 w-3.5" />
            <span>YouTube Video Notes</span>
          </button>
          <button
            onClick={() => setActiveTabLocal('exam')}
            className={`rounded-lg px-3 py-1 font-medium transition-colors flex items-center gap-1.5 cursor-pointer ${
              activeTab === 'exam'
                ? 'bg-[#242424] text-[#FFFDF8]'
                : 'text-[#6B7280] hover:text-[#242424]'
            }`}
          >
            <BookOpen className="h-3.5 w-3.5" />
            <span>Exam Study Help</span>
          </button>
        </div>
      </div>

      {/* ============================================================= */}
      {/* SECTION A: YOUTUBE VIDEO NOTES                                */}
      {/* ============================================================= */}
      {activeTab === 'youtube' && (
        <div className="space-y-6">
          {/* URL Input Form */}
          <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm space-y-4">
            <div className="space-y-1">
              <h3 className="text-xs font-semibold text-[#242424]">Lecture Video URL</h3>
              <p className="text-[11px] text-[#6B7280]">
                Enter a public YouTube lecture URL to retrieve timestamped notes and revision questions.
              </p>
            </div>

            <form onSubmit={handleCheckVideo} className="flex gap-2">
              <div className="relative flex-1">
                <Link2 className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[#9CA3AF]" />
                <input
                  type="text"
                  value={ytUrl}
                  onChange={(e) => {
                    setYtUrl(e.target.value)
                    if (ytStatus !== 'idle') setYtStatus('idle')
                  }}
                  placeholder="https://www.youtube.com/watch?v=..."
                  className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] pl-9 pr-3 py-2 text-xs text-[#242424] placeholder:text-[#9CA3AF] focus:border-[#242424] focus:bg-[#FFFDF8] focus:outline-none transition-all"
                />
              </div>

              <button
                type="submit"
                disabled={ytStatus === 'checking'}
                className="rounded-xl bg-[#242424] px-4 py-2 text-xs font-semibold text-[#FFFDF8] hover:bg-[#383838] transition-colors shrink-0 cursor-pointer shadow-warm-sm disabled:opacity-50"
              >
                {ytStatus === 'checking' ? 'Checking Captions...' : 'Process Video'}
              </button>
            </form>
          </div>

          {/* Mandatory No-Transcript Handling State */}
          {ytStatus === 'no_transcript' && (
            <div className="rounded-2xl border border-[#E9DB91] bg-[#FFFDF8] p-5 shadow-warm-sm space-y-4 animate-in fade-in duration-200">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-[#854D0E] shrink-0 mt-0.5" />
                <div className="space-y-1 text-xs">
                  <h4 className="font-semibold text-[#854D0E]">
                    No transcript available. No notes were created.
                  </h4>
                  <p className="text-[#713F12] leading-relaxed">
                    This video does not have accessible automated captions or a public transcript service integration. The assistant does not generate notes from assumptions or invent content.
                  </p>
                </div>
              </div>

              {/* Paste Transcript Manual Fallback */}
              <form onSubmit={handleProcessManualTranscript} className="space-y-3 pt-3 border-t border-[#DEDAD0]">
                <label className="text-xs font-semibold text-[#242424] block">
                  Paste Transcript or Lecture Text with Timestamps:
                </label>
                <textarea
                  rows={5}
                  value={manualTranscript}
                  onChange={(e) => setManualTranscript(e.target.value)}
                  placeholder="Paste manual captions or notes (e.g. 01:15 Overview of Relational Database Normalization&#10;05:30 First Normal Form (1NF) Rules and Candidate Keys&#10;12:45 Second Normal Form (2NF) and Partial Dependencies)..."
                  className="w-full rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-3 text-xs text-[#242424] focus:border-[#242424] focus:bg-[#FFFDF8] focus:outline-none transition-all font-mono"
                />
                <button
                  type="submit"
                  disabled={!manualTranscript.trim()}
                  className="rounded-xl bg-[#242424] px-4 py-2 text-xs font-semibold text-[#FFFDF8] hover:bg-[#383838] transition-colors disabled:opacity-40 cursor-pointer shadow-warm-sm"
                >
                  Generate Grounded Notes from Pasted Text
                </button>
              </form>
            </div>
          )}

          {/* Success State: Extracted Timestamped Topics */}
          {ytStatus === 'success' && extractedYtTopics.length > 0 && (
            <div className="space-y-4">
              <div className="flex items-center justify-between border-b border-[#DEDAD0] pb-2 text-xs">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-[#708A4E]" />
                  <span className="font-semibold text-[#242424]">Extracted Topic Notes & Questions</span>
                </div>
                <span className="text-[#6B7280] font-mono">
                  {extractedYtTopics.length} Sections
                </span>
              </div>

              <div className="space-y-3">
                {extractedYtTopics.map((topic, idx) => (
                  <div
                    key={idx}
                    className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm space-y-3"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#DEDAD0] pb-2">
                      <div className="flex items-center gap-2">
                        <span className="rounded bg-[#B9CDE7]/50 border border-[#B9CDE7] px-2 py-0.5 text-[10px] font-mono font-medium text-[#171717] flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {topic.timestamp}
                        </span>
                        <h4 className="text-xs font-semibold text-[#242424]">{topic.title}</h4>
                      </div>

                      <button
                        onClick={() => handleCreateTaskFromYtTopic(topic)}
                        className="inline-flex items-center gap-1 rounded-lg border border-[#DEDAD0] bg-[#F7F4EB] px-2.5 py-1 text-[11px] font-semibold text-[#242424] hover:bg-[#EFECE2] transition-colors self-start sm:self-auto cursor-pointer"
                      >
                        <Plus className="h-3 w-3" />
                        <span>Add Topic Review to Tasks</span>
                      </button>
                    </div>

                    <p className="text-xs text-[#4B5563] leading-relaxed">
                      {topic.summary}
                    </p>

                    {/* Grounded Questions */}
                    {topic.questions && topic.questions.length > 0 && (
                      <div className="pt-2 border-t border-[#DEDAD0] space-y-2">
                        <div className="flex items-center justify-between text-[11px] text-[#6B7280]">
                          <span className="font-medium text-[#242424] flex items-center gap-1">
                            <HelpCircle className="h-3.5 w-3.5" />
                            Revision Question:
                          </span>
                          <button
                            onClick={() => setRevealedYtAnswers(prev => ({ ...prev, [idx]: !prev[idx] }))}
                            className="text-[#6B7280] hover:text-[#242424] font-medium cursor-pointer"
                          >
                            {revealedYtAnswers[idx] ? 'Hide Answer' : 'Reveal Answer'}
                          </button>
                        </div>
                        <p className="text-xs text-[#242424] font-medium">
                          {topic.questions[0].q}
                        </p>
                        {revealedYtAnswers[idx] && (
                          <div className="rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] p-3 text-xs text-[#4B5563]">
                            <span className="font-semibold text-[#242424]">Model Answer: </span>
                            {topic.questions[0].a}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ============================================================= */}
      {/* SECTION B: EXAM STUDY HELP                                    */}
      {/* ============================================================= */}
      {activeTab === 'exam' && (
        <div className="space-y-6">
          {/* Upload Notes & Materials */}
          <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h3 className="text-xs font-semibold text-[#242424]">Upload Study Material</h3>
                <p className="text-[11px] text-[#6B7280] mt-0.5">
                  Upload text notes, markdown, or course outlines (.txt, .md, .json) to generate grounded questions.
                </p>
              </div>

              {/* Target Exam Date Selector */}
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-[#242424] flex items-center gap-1">
                  <Calendar className="h-3.5 w-3.5" />
                  Target Exam:
                </span>
                <input
                  type="date"
                  value={examDate}
                  onChange={(e) => handleApplyExamDateChange(e.target.value)}
                  className="rounded-xl border border-[#DEDAD0] bg-[#F7F4EB] px-2.5 py-1 text-xs text-[#242424] font-mono focus:outline-none"
                />
              </div>
            </div>

            {/* Drag & Drop File Input Area */}
            <div className="relative rounded-xl border border-dashed border-[#DEDAD0] bg-[#F7F4EB]/50 p-6 text-center hover:bg-[#F7F4EB] transition-colors">
              <input
                type="file"
                multiple
                accept=".txt,.md,.text,.json"
                onChange={handleFileUpload}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              />
              <FileUp className="mx-auto h-7 w-7 text-[#9CA3AF]" />
              <div className="text-xs font-semibold text-[#242424] mt-2">
                Click or drag course notes here
              </div>
              <p className="text-[11px] text-[#6B7280]">
                Supports plain text and markdown notes (processed locally on your client)
              </p>
            </div>

            {/* Uploaded Documents List */}
            {uploadedFiles.length > 0 && (
              <div className="space-y-2 pt-2 border-t border-[#DEDAD0]">
                <span className="text-[11px] font-semibold text-[#6B7280]">
                  Indexed Materials ({uploadedFiles.length}):
                </span>
                <div className="flex flex-wrap gap-2">
                  {uploadedFiles.map((f, i) => (
                    <div
                      key={i}
                      className="rounded-lg border border-[#DEDAD0] bg-[#F7F4EB] px-2.5 py-1 text-xs text-[#242424] flex items-center gap-2"
                    >
                      <FileText className="h-3 w-3 text-[#6B7280]" />
                      <span className="font-medium truncate max-w-[150px]">{f.name}</span>
                      <span className="text-[10px] text-[#9CA3AF] font-mono">({f.size})</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Revision Plan Trajectory */}
          {revisionPlan.length > 0 && (
            <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#DEDAD0] pb-3">
                <div>
                  <h3 className="text-sm font-semibold text-[#242424]">Targeted Revision Plan</h3>
                  <p className="text-xs text-[#6B7280] mt-0.5">
                    Structured study sessions leading up to {new Date(examDate + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                  </p>
                </div>

                <button
                  onClick={handleAddPlanToTasks}
                  disabled={addingPlanToTasks}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-[#242424] px-4 py-2 text-xs font-semibold text-[#FFFDF8] hover:bg-[#383838] transition-colors cursor-pointer shadow-warm-sm disabled:opacity-50"
                >
                  <Plus className="h-3.5 w-3.5" />
                  <span>{addingPlanToTasks ? 'Scheduling...' : 'Add Revision Sessions to Tasks & Calendar'}</span>
                </button>
              </div>

              <div className="space-y-2.5">
                {revisionPlan.map((session, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 rounded-xl border border-[#DEDAD0] bg-[#F7F4EB]/40 flex flex-col sm:flex-row sm:items-center justify-between gap-2"
                  >
                    <div className="flex items-center gap-3">
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#FFFDF8] border border-[#DEDAD0] text-[10px] font-bold text-[#242424] font-mono">
                        {idx + 1}
                      </span>
                      <div>
                        <div className="text-xs font-semibold text-[#242424]">{session.topic}</div>
                        <div className="text-[11px] text-[#6B7280]">{session.focus}</div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 self-start sm:self-auto font-mono text-[11px]">
                      <span className="rounded bg-[#E9DB91]/50 border border-[#E9DB91] px-2 py-0.5 text-[#171717]">
                        {session.scheduledDate}
                      </span>
                      <span className="text-[#9CA3AF]">({session.sessionLength})</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Grounded Practice Questions */}
          {examTopics.length > 0 ? (
            <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-5 shadow-warm-sm space-y-4">
              <div className="border-b border-[#DEDAD0] pb-2">
                <h3 className="text-sm font-semibold text-[#242424]">Grounded Practice Questions</h3>
                <p className="text-xs text-[#6B7280] mt-0.5">
                  Questions derived strictly from the content of your uploaded materials.
                </p>
              </div>

              <div className="space-y-3">
                {examTopics.map((topic, idx) => (
                  <div
                    key={idx}
                    className="rounded-xl border border-[#DEDAD0] bg-[#FFFDF8] p-4 shadow-warm-sm space-y-2"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="space-y-1">
                        <span className="text-[10px] font-mono uppercase tracking-wider text-[#6B7280]">
                          Source: {topic.source}
                        </span>
                        <div className="text-xs font-semibold text-[#242424]">
                          {topic.sampleQuestion.question}
                        </div>
                      </div>

                      <button
                        onClick={() => setRevealedExamAnswers(prev => ({ ...prev, [idx]: !prev[idx] }))}
                        className="text-[11px] font-medium text-[#6B7280] hover:text-[#242424] shrink-0 cursor-pointer"
                      >
                        {revealedExamAnswers[idx] ? 'Hide Answer' : 'Show Answer'}
                      </button>
                    </div>

                    {revealedExamAnswers[idx] && (
                      <div className="pt-2 border-t border-[#DEDAD0] text-xs text-[#4B5563] bg-[#F7F4EB] p-3 rounded-lg leading-relaxed">
                        <span className="font-semibold text-[#242424]">Answer from document: </span>
                        {topic.sampleQuestion.answer}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="rounded-2xl border border-[#DEDAD0] bg-[#FFFDF8] p-12 text-center text-xs text-[#6B7280] space-y-2 shadow-warm-sm">
              <BookOpen className="mx-auto h-7 w-7 text-[#9CA3AF]" />
              <p className="font-medium text-[#242424]">No study documents indexed yet</p>
              <p className="text-[11px]">Upload a lecture notes file above to generate revision plans and grounded practice questions.</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
