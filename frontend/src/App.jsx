import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Bot, UploadCloud, User, Volume2, VolumeX } from 'lucide-react'
import {
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut,
} from 'firebase/auth'
import FinalReportModal from './FinalReportModal'
import Visualizer from './Visualizer'
import VoiceOrb from './VoiceOrb'
import { auth } from './firebase'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

function App() {
  const [messages, setMessages] = useState([])
  const [authUser, setAuthUser] = useState(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [authError, setAuthError] = useState('')
  const [authEmail, setAuthEmail] = useState('')
  const [authPassword, setAuthPassword] = useState('')
  const [isSigningUp, setIsSigningUp] = useState(false)
  const [metrics, setMetrics] = useState({
    average_technical_accuracy: 0,
    average_communication_clarity: 0,
    average_confidence_score: 0,
    average_confidence_label: 'Low',
  })
  const [isRecording, setIsRecording] = useState(false)
  const [isSpeakerMuted, setIsSpeakerMuted] = useState(false)
  const [isSpeechSupported, setIsSpeechSupported] = useState(true)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [isTyping, setIsTyping] = useState(false)
  const [liveTranscript, setLiveTranscript] = useState('')
  const [showFinalize, setShowFinalize] = useState(false)
  const [finalReport, setFinalReport] = useState({
    overall_verdict: 'No Hire',
    key_strengths: [],
    critical_gaps: [],
    culture_fit_score: 0,
  })
  const [isFinalizing, setIsFinalizing] = useState(false)
  const isProcessing = isTyping || isFinalizing
  const [hasStarted, setHasStarted] = useState(false)
  const [interviewTerminated, setInterviewTerminated] = useState(false)
  const [sessionId, setSessionId] = useState(null)
  const [resumeId, setResumeId] = useState(null)
  const [candidateProfile, setCandidateProfile] = useState(null)
  const bottomRef = useRef(null)
  const previousMessageCount = useRef(0)
  const recognitionRef = useRef(null)
  const silenceTimerRef = useRef(null)
  const suppressAutoSendRef = useRef(false)
  const lastWordCountRef = useRef(0)
  const startListeningRef = useRef(null)
  const finalTranscriptRef = useRef('')
  const lastTranscriptRef = useRef('')
  const preferredVoiceRef = useRef(null)
  const hasAutoFinalizedRef = useRef(false)

  const findMaleVoice = useCallback((voices) => {
    if (!voices?.length) return null
    return (
      voices.find((voice) => voice.name === 'Google US English Male') ||
      voices.find((voice) => voice.name === 'Microsoft David - English (United States)') ||
      voices.find((voice) => voice.name === 'Daniel' || voice.name.includes('Daniel')) ||
      null
    )
  }, [])

  const loadVoices = useCallback(() => {
    if (!('speechSynthesis' in window)) return []
    const voices = window.speechSynthesis.getVoices()
    const maleVoice = findMaleVoice(voices)
    preferredVoiceRef.current = maleVoice || null
    return voices
  }, [findMaleVoice])

  // VoiceManager: text-to-speech output for Sura.
  const speakText = useCallback(
    (text) => {
      if (!text || isSpeakerMuted || !('speechSynthesis' in window)) return
      const voices = loadVoices()
      const utterance = new SpeechSynthesisUtterance(text)
      const maleVoice = findMaleVoice(voices)
      if (maleVoice) {
        utterance.voice = maleVoice
      }
      utterance.rate = 1.0
      utterance.pitch = 0.9
      utterance.volume = 1
      utterance.onstart = () => setIsSpeaking(true)
      utterance.onend = () => {
        setIsSpeaking(false)
        if (!interviewTerminated && hasStarted && !isTyping) {
          startListeningRef.current?.()
        }
      }
      utterance.onerror = () => setIsSpeaking(false)
      window.speechSynthesis.cancel()
      window.speechSynthesis.speak(utterance)
    },
    [findMaleVoice, hasStarted, interviewTerminated, isSpeakerMuted, isTyping, loadVoices]
  )

  const progressBars = useMemo(
    () => [
      {
        label: 'Technical Accuracy',
        value: metrics.average_technical_accuracy,
        color: 'bg-emerald-500',
      },
      {
        label: 'Communication',
        value: metrics.average_communication_clarity,
        color: 'bg-blue-500',
      },
      {
        label: 'Confidence',
        value: Math.round((metrics.average_confidence_score / 3) * 10),
        color: 'bg-amber-500',
      },
    ],
    [metrics]
  )

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping])

  useEffect(() => {
    if (messages.length <= previousMessageCount.current) return
    const latest = messages[messages.length - 1]
    if (latest?.role === 'assistant') {
      try {
        const AudioContext = window.AudioContext || window.webkitAudioContext
        const context = new AudioContext()
        const oscillator = context.createOscillator()
        const gainNode = context.createGain()
        oscillator.type = 'sine'
        oscillator.frequency.value = 520
        gainNode.gain.value = 0.04
        oscillator.connect(gainNode)
        gainNode.connect(context.destination)
        oscillator.start()
        oscillator.stop(context.currentTime + 0.08)
        oscillator.onended = () => context.close()
      } catch (error) {
        console.warn('Audio not available', error)
      }
      speakText(latest.content)
    }
    previousMessageCount.current = messages.length
  }, [messages, speakText])

  useEffect(() => {
    if (!sessionId) return
    const intervalId = setInterval(() => {
      fetchMetrics(sessionId)
    }, 5000)
    return () => clearInterval(intervalId)
  }, [sessionId])

  useEffect(() => {
    if (!sessionId || showFinalize || hasAutoFinalizedRef.current) return
    const assistantMessages = messages.filter((message) => message.role === 'assistant')
    const interviewQuestionCount = Math.max(0, assistantMessages.length - 1)
    if (interviewQuestionCount >= 5) {
      hasAutoFinalizedRef.current = true
      finalizeInterview()
    }
  }, [messages, sessionId, showFinalize])

  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    setIsSpeechSupported(Boolean(SpeechRecognition))
  }, [])

  useEffect(() => {
    if (!('speechSynthesis' in window)) return
    const handleVoicesChanged = () => {
      loadVoices()
    }
    loadVoices()
    window.speechSynthesis.addEventListener('voiceschanged', handleVoicesChanged)
    return () => {
      window.speechSynthesis.removeEventListener('voiceschanged', handleVoicesChanged)
      window.speechSynthesis.cancel()
    }
  }, [loadVoices])

  useEffect(() => {
    return () => {
      recognitionRef.current?.abort?.()
      window.speechSynthesis?.cancel?.()
      setIsSpeaking(false)
    }
  }, [])

  useEffect(() => {
    if (!hasStarted || interviewTerminated) {
      recognitionRef.current?.stop?.()
      setIsRecording(false)
    }
  }, [hasStarted, interviewTerminated])

  useEffect(() => {
    if (!isRecording) return
    const words = liveTranscript.trim().split(/\s+/).filter(Boolean)
    const wordCount = words.length
    if (wordCount === 0 || wordCount === lastWordCountRef.current) return

    lastWordCountRef.current = wordCount
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current)
    }
    silenceTimerRef.current = setTimeout(() => {
      recognitionRef.current?.stop?.()
    }, 1500)
  }, [isRecording, liveTranscript])

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      setAuthUser(user)
      setAuthLoading(false)
    })
    return () => unsubscribe()
  }, [])

  const resetInterviewState = () => {
    setMessages([])
    setSessionId(null)
    setResumeId(null)
    setCandidateProfile(null)
    setHasStarted(false)
    setInterviewTerminated(false)
    setFinalReport({
      overall_verdict: 'No Hire',
      key_strengths: [],
      critical_gaps: [],
      culture_fit_score: 0,
    })
    setShowFinalize(false)
    setMetrics({
      average_technical_accuracy: 0,
      average_communication_clarity: 0,
      average_confidence_score: 0,
      average_confidence_label: 'Low',
    })
  }

  const handleAuthSubmit = async (event) => {
    event.preventDefault()
    setAuthError('')
    try {
      if (isSigningUp) {
        await createUserWithEmailAndPassword(auth, authEmail.trim(), authPassword)
      } else {
        await signInWithEmailAndPassword(auth, authEmail.trim(), authPassword)
      }
    } catch (error) {
      setAuthError(error?.message || 'Authentication failed')
    }
  }

  const handleSignOut = async () => {
    await signOut(auth)
    resetInterviewState()
  }

  const getAuthHeaders = async () => {
    if (!authUser) return {}
    const token = await authUser.getIdToken()
    return { Authorization: `Bearer ${token}` }
  }

  const uploadResume = async (file) => {
    if (!authUser) {
      throw new Error('Please sign in to upload a resume.')
    }
    const formData = new FormData()
    formData.append('file', file)
    const authHeaders = await getAuthHeaders()
    const response = await fetch(`${API_BASE}/upload-resume`, {
      method: 'POST',
      body: formData,
      headers: authHeaders,
    })
    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(errorText || 'Upload failed')
    }
    return response.json()
  }

  const startInterview = async (profile) => {
    const authHeaders = await getAuthHeaders()
    const response = await fetch(`${API_BASE}/start-interview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders },
      body: JSON.stringify({
        candidate_profile: profile,
        resume_id: resumeId,
        job_description: '',
      }),
    })
    if (!response.ok) {
      throw new Error('Start interview failed')
    }
    return response.json()
  }

  const sendMessage = async (text) => {
    const authHeaders = await getAuthHeaders()
    const response = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders },
      body: JSON.stringify({
        session_id: sessionId,
        user_text: text,
      }),
    })
    if (!response.ok) {
      throw new Error('Chat failed')
    }
    return response.json()
  }

  const finalizeInterview = async () => {
    if (!sessionId || isFinalizing) return
    setIsFinalizing(true)
    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch(`${API_BASE}/session/report/${sessionId}`, {
        headers: authHeaders,
      })
      if (!response.ok) {
        throw new Error('Finalize failed')
      }
      const data = await response.json()
      setFinalReport({
        overall_verdict: data.overall_verdict || 'No Hire',
        key_strengths: data.key_strengths || [],
        critical_gaps: data.critical_gaps || [],
        culture_fit_score: data.culture_fit_score || 0,
      })
      setShowFinalize(true)
    } catch (error) {
      console.error('Failed to finalize interview', error)
    } finally {
      setIsFinalizing(false)
    }
  }

  const handleEndInterview = () => {
    window.speechSynthesis?.cancel?.()
    suppressAutoSendRef.current = true
    recognitionRef.current?.stop?.()
    setIsRecording(false)
    setIsSpeaking(false)
    setInterviewTerminated(true)
    setHasStarted(false)
    finalizeInterview()
  }

  const fetchMetrics = async (id) => {
    if (!id) return
    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch(`${API_BASE}/session/metrics/${id}`, {
        headers: authHeaders,
      })
      if (!response.ok) {
        throw new Error('Metrics fetch failed')
      }
      const data = await response.json()
      setMetrics(data)
    } catch (error) {
      console.error('Failed to fetch metrics', error)
    }
  }

  const handleResumeUpload = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    event.target.value = ''
    setIsUploading(true)
    try {
      const uploadResponse = await uploadResume(file)
      const profile = uploadResponse.profile || uploadResponse
      if (uploadResponse.resume_id) {
        setResumeId(uploadResponse.resume_id)
      }
      setCandidateProfile(profile)
      const { session_id, message } = await startInterview(profile)
      hasAutoFinalizedRef.current = false
      setShowFinalize(false)
      setFinalReport({
        overall_verdict: 'No Hire',
        key_strengths: [],
        critical_gaps: [],
        culture_fit_score: 0,
      })
      setSessionId(session_id)
      setHasStarted(true)
      setInterviewTerminated(false)
      setMessages([{ id: Date.now(), role: 'assistant', content: message }])
      await fetchMetrics(session_id)
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now(),
          role: 'assistant',
          content:
            `Upload failed: ${error?.message || 'Unknown error'}. ` +
            'Please confirm the backend is running and the API key is set.',
        },
      ])
    } finally {
      setIsUploading(false)
    }
  }

  const handleSend = async (overrideText) => {
    const messageText = (overrideText ?? '').trim()
    if (!messageText || !sessionId || isTyping || !hasStarted || interviewTerminated) return
    if (isRecording) {
      suppressAutoSendRef.current = true
      recognitionRef.current?.stop?.()
      setIsRecording(false)
    }
    const userMessage = { id: Date.now(), role: 'user', content: messageText }
    setMessages((prev) => [...prev, userMessage])
    setIsTyping(true)

    try {
      const reply = await sendMessage(userMessage.content)
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          role: 'assistant',
          content: reply.message,
        },
      ])
      await fetchMetrics(sessionId)
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          role: 'assistant',
          content: 'Sorry, I had trouble responding. Please try again.',
        },
      ])
    } finally {
      setIsTyping(false)
    }
  }

  // VoiceManager: speech-to-text input for the candidate.
  const startListening = () => {
    if (!hasStarted || interviewTerminated || isTyping || isRecording) return
    if (window.speechSynthesis?.speaking || isSpeaking) {
      window.speechSynthesis?.cancel?.()
    }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) {
      setIsSpeechSupported(false)
      setIsRecording(false)
      return
    }

    setIsSpeechSupported(true)
    const recognition = recognitionRef.current || new SpeechRecognition()
    recognitionRef.current = recognition
    recognition.lang = 'en-US'
    recognition.interimResults = true
    recognition.continuous = true

    finalTranscriptRef.current = ''
    lastTranscriptRef.current = ''
    setLiveTranscript('')
    lastWordCountRef.current = 0

    recognition.onresult = (event) => {
      if (window.speechSynthesis?.speaking) {
        window.speechSynthesis.cancel()
      }
      let interimTranscript = ''
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i]
        if (result.isFinal) {
          finalTranscriptRef.current += result[0].transcript
        } else {
          interimTranscript += result[0].transcript
        }
      }
      const combined = `${finalTranscriptRef.current} ${interimTranscript}`.trim()
      lastTranscriptRef.current = combined
      setLiveTranscript(combined)
    }

    recognition.onerror = (event) => {
      console.warn('Speech recognition error', event?.error)
      setIsRecording(false)
    }

    recognition.onend = () => {
      setIsRecording(false)
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current)
        silenceTimerRef.current = null
      }
      if (suppressAutoSendRef.current) {
        suppressAutoSendRef.current = false
        setLiveTranscript('')
        lastWordCountRef.current = 0
        finalTranscriptRef.current = ''
        lastTranscriptRef.current = ''
        return
      }
      const finalText = finalTranscriptRef.current.trim() || lastTranscriptRef.current.trim()
      if (finalText && finalText.split(/\s+/).filter(Boolean).length > 3) {
        handleSend(finalText)
      }
      setLiveTranscript('')
      lastWordCountRef.current = 0
      finalTranscriptRef.current = ''
      lastTranscriptRef.current = ''
    }

    recognition.start()
    setIsRecording(true)
  }

  const stopListening = () => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current)
      silenceTimerRef.current = null
    }
    recognitionRef.current?.stop?.()
    setIsRecording(false)
  }

  useEffect(() => {
    startListeningRef.current = startListening
  }, [startListening])

  useEffect(() => {
    if (
      !sessionId ||
      !isSpeechSupported ||
      !hasStarted ||
      interviewTerminated ||
      isRecording ||
      isSpeaking ||
      isTyping ||
      window.speechSynthesis?.speaking
    )
      return
    startListening()
  }, [sessionId, isSpeechSupported, hasStarted, interviewTerminated, isRecording, isSpeaking, isTyping])

  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-900 text-slate-100">
        Loading...
      </div>
    )
  }

  if (!authUser) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-900 text-slate-100">
        <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/5 p-6 shadow-2xl shadow-indigo-500/20">
          <h1 className="text-xl font-semibold text-white">
            {isSigningUp ? 'Create account' : 'Sign in'}
          </h1>
          <p className="mt-2 text-sm text-slate-300">
            Use your email and password to continue.
          </p>
          <form className="mt-6 space-y-4" onSubmit={handleAuthSubmit}>
            <div>
              <label className="text-xs uppercase tracking-wide text-slate-400">Email</label>
              <input
                type="email"
                className="mt-2 w-full rounded-xl border border-white/10 bg-slate-900/60 px-4 py-2 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/60"
                value={authEmail}
                onChange={(event) => setAuthEmail(event.target.value)}
                required
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-wide text-slate-400">Password</label>
              <input
                type="password"
                className="mt-2 w-full rounded-xl border border-white/10 bg-slate-900/60 px-4 py-2 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/60"
                value={authPassword}
                onChange={(event) => setAuthPassword(event.target.value)}
                required
              />
            </div>
            {authError && <p className="text-sm text-rose-300">{authError}</p>}
            <button
              type="submit"
              className="w-full rounded-xl bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-400"
            >
              {isSigningUp ? 'Create account' : 'Sign in'}
            </button>
          </form>
          <button
            type="button"
            className="mt-4 text-sm text-slate-300 underline underline-offset-4"
            onClick={() => setIsSigningUp((prev) => !prev)}
          >
            {isSigningUp ? 'Already have an account? Sign in' : 'New here? Create an account'}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="relative min-h-screen bg-slate-900 text-slate-100">
      <div className="absolute inset-0">
        <div className="particle-layer" />
      </div>
      <div className="relative mx-auto flex min-h-screen max-w-6xl gap-6 px-6 py-8">
        <motion.aside
          className="w-80 rounded-3xl border border-white/15 bg-white/10 p-6 shadow-2xl shadow-indigo-500/25 backdrop-blur-2xl"
          animate={
            metrics.average_technical_accuracy >= 8
              ? { scale: [1, 1.01, 1] }
              : { scale: 1 }
          }
          transition={{ duration: 3, repeat: metrics.average_technical_accuracy >= 8 ? Infinity : 0 }}
        >
          <div className="mb-8">
            <p className="text-sm uppercase tracking-[0.3em] text-slate-300">Interview</p>
            <h1 className="mt-3 text-2xl font-semibold text-white">Performance Snapshot</h1>
            <p className="mt-2 text-sm text-slate-300">
              Real-time scoring based on the conversation.
            </p>
          </div>

          {candidateProfile && (
            <div className="mb-8 rounded-2xl border border-white/15 bg-white/10 p-4 text-sm text-slate-200 shadow-lg shadow-slate-950/40 backdrop-blur-xl">
              <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Candidate</p>
              <p className="mt-2 text-base font-semibold text-white">
                {candidateProfile.full_name}
              </p>
              {candidateProfile.technical_stack?.length ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {candidateProfile.technical_stack.slice(0, 6).map((skill) => (
                    <span
                      key={skill}
                      className="rounded-full border border-white/10 bg-slate-900/70 px-3 py-1 text-xs text-slate-200"
                    >
                      {skill}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          )}

          <div className="space-y-6">
            {progressBars.map((item) => (
              <div key={item.label}>
                <div className="flex items-center justify-between text-sm text-slate-200">
                  <span>{item.label}</span>
                  <span>{item.value}</span>
                </div>
                <div className="mt-2 h-2 rounded-full bg-white/10">
                  <div
                    className="h-2 rounded-full bg-gradient-to-r from-cyan-400 to-blue-600 shadow-lg shadow-cyan-500/30 transition-all duration-700"
                    style={{ width: `${Math.min(item.value * 10, 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>

          <div className="mt-8 rounded-2xl border border-white/15 bg-white/10 p-4 text-sm text-slate-300 shadow-lg shadow-slate-950/40 backdrop-blur-xl">
            Confidence signal: <span className="text-white">{metrics.average_confidence_label}</span>
          </div>
        </motion.aside>

        <main className="flex flex-1 flex-col rounded-3xl border border-white/10 bg-white/5 shadow-2xl shadow-indigo-500/20 backdrop-blur-xl">
          <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
            <div>
              <div className="flex items-center gap-3">
                <span className={`pulse-dot ${isTyping ? 'pulse-dot--active' : ''}`} />
                <h2 className="text-lg font-semibold">Sura • Lead Engineer</h2>
              </div>
              <p className="text-sm text-slate-400">Behavioral + Technical Interview</p>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => {
                  setIsSpeakerMuted((prev) => {
                    const next = !prev
                    if (next) {
                      window.speechSynthesis?.cancel?.()
                      setIsSpeaking(false)
                    }
                    return next
                  })
                }}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs text-slate-200 transition hover:bg-white/10"
              >
                {isSpeakerMuted ? (
                  <VolumeX className="h-4 w-4 text-rose-200" />
                ) : (
                  <Volume2 className="h-4 w-4 text-emerald-200" />
                )}
                Speaker
              </button>
              <button
                type="button"
                onClick={handleSignOut}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs text-slate-200 transition hover:bg-white/10"
              >
                Sign out
              </button>
              <button
                type="button"
                onClick={handleEndInterview}
                disabled={!sessionId || isFinalizing}
                className="inline-flex items-center gap-2 rounded-full border border-rose-400/40 bg-rose-500/20 px-4 py-2 text-sm text-rose-100 transition hover:bg-rose-500/30 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isFinalizing ? 'Finalizing...' : 'End Interview'}
              </button>
              <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200 transition hover:bg-white/10">
                <UploadCloud className="h-4 w-4" />
                {isUploading ? 'Uploading...' : 'Upload Resume'}
                <input type="file" className="hidden" onChange={handleResumeUpload} />
              </label>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-6">
            <AnimatePresence initial={false}>
              {messages.map((message) => (
                <motion.div
                  key={message.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.2 }}
                  className={`mb-4 flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  {message.role === 'assistant' ? (
                    <div className="flex max-w-2xl items-start gap-3">
                      <div className="flex flex-col items-center gap-2">
                        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-500/20 text-indigo-200 shadow-lg shadow-indigo-500/40">
                          <Bot className="h-5 w-5" />
                        </span>
                        <Visualizer isActive={isSpeaking} />
                      </div>
                      <div className="border-l border-indigo-400/60 pl-4 text-base text-slate-100">
                        {message.content}
                      </div>
                    </div>
                  ) : (
                    <div className="flex max-w-xl items-start gap-3 rounded-2xl border border-white/10 bg-white/10 px-4 py-3 text-sm text-slate-100 shadow-lg backdrop-blur">
                      <p className="leading-relaxed">{message.content}</p>
                      <User className="mt-0.5 h-5 w-5 text-indigo-100" />
                    </div>
                  )}
                </motion.div>
              ))}
            </AnimatePresence>

            {isTyping && (
              <div className="mb-4 flex justify-start">
                <div className="flex items-center gap-3 rounded-2xl bg-white/5 px-4 py-3 text-sm text-slate-200 shadow-lg backdrop-blur">
                  <span className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-500/20 text-indigo-200 shadow-lg shadow-indigo-500/40">
                    <Bot className="h-5 w-5" />
                  </span>
                  <div className="typing-dots">
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="flex flex-col items-center px-6 pb-6">
            <p className="mb-3 text-xs uppercase tracking-[0.3em] text-slate-400">
              {isRecording
                ? 'Listening...'
                : isProcessing
                  ? 'Thinking...'
                  : isSpeaking
                    ? 'Sura is speaking...'
                    : 'Ready'}
            </p>
            <div
              className={`rounded-full p-4 transition ${
                isRecording
                  ? 'shadow-[0_0_30px_rgba(248,113,113,0.4)]'
                  : 'shadow-[0_0_16px_rgba(59,130,246,0.2)]'
              }`}
            >
              <VoiceOrb
                status={
                  isRecording
                    ? 'listening'
                    : isProcessing
                      ? 'processing'
                      : isSpeaking
                        ? 'speaking'
                        : 'idle'
                }
              />
            </div>
          </div>

          
        </main>
      </div>

      {showFinalize && (
        <FinalReportModal
          report={finalReport}
          metrics={metrics}
          onClose={() => setShowFinalize(false)}
          onRestart={() => window.location.reload()}
          onPrint={() => window.print()}
        />
      )}
    </div>
  )
}

export default App
