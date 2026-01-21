import { useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'

const BASE_SCALE = 1
const MAX_SCALE = 1.35

const clamp = (value, min, max) => Math.min(Math.max(value, min), max)

function VoiceOrb({ status = 'idle' }) {
  const [scale, setScale] = useState(BASE_SCALE)
  const audioContextRef = useRef(null)
  const analyserRef = useRef(null)
  const dataArrayRef = useRef(null)
  const rafRef = useRef(null)

  useEffect(() => {
    let stream = null
    let isMounted = true

    const setupAudio = async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        const audioContext = new (window.AudioContext || window.webkitAudioContext)()
        const analyser = audioContext.createAnalyser()
        analyser.fftSize = 256
        const source = audioContext.createMediaStreamSource(stream)
        source.connect(analyser)

        audioContextRef.current = audioContext
        analyserRef.current = analyser
        dataArrayRef.current = new Uint8Array(analyser.frequencyBinCount)

        const update = () => {
          if (!isMounted || !analyserRef.current || !dataArrayRef.current) return
          analyserRef.current.getByteFrequencyData(dataArrayRef.current)
          const sum = dataArrayRef.current.reduce((acc, val) => acc + val, 0)
          const average = sum / dataArrayRef.current.length
          const normalized = clamp(average / 255, 0, 1)
          const nextScale = BASE_SCALE + normalized * (MAX_SCALE - BASE_SCALE)
          setScale(nextScale)
          rafRef.current = requestAnimationFrame(update)
        }

        update()
      } catch (error) {
        console.warn('Microphone access not available', error)
      }
    }

    setupAudio()

    return () => {
      isMounted = false
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      if (stream) {
        stream.getTracks().forEach((track) => track.stop())
      }
      if (audioContextRef.current) {
        audioContextRef.current.close()
      }
    }
  }, [])

  const orbStyles = useMemo(() => {
    if (status === 'processing') {
      return {
        background: 'rgb(168, 85, 247)',
        boxShadow: '0 0 50px rgba(168, 85, 247, 0.5)',
      }
    }
    if (status === 'listening') {
      return {
        background: 'rgb(248, 113, 113)',
        boxShadow: '0 0 50px rgba(248, 113, 113, 0.55)',
      }
    }
    return {
      background: 'rgb(59, 130, 246)',
      boxShadow: '0 0 50px rgba(59, 130, 246, 0.5)',
    }
  }, [status])

  const animateConfig =
    status === 'processing'
      ? { scale: [1, 1.08, 1] }
      : status === 'listening'
        ? { scale }
        : { scale: 1 }

  const transitionConfig =
    status === 'processing'
      ? { duration: 2.4, repeat: Infinity, ease: 'easeInOut' }
      : status === 'listening'
        ? { type: 'spring', stiffness: 120, damping: 12 }
        : { duration: 0.2 }

  return (
    <motion.div
      aria-label={status}
      className="h-24 w-24 rounded-full"
      style={orbStyles}
      animate={animateConfig}
      transition={transitionConfig}
    />
  )
}

export default VoiceOrb
