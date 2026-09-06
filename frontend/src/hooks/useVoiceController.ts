// React hook wrapping the imperative VoiceInteractionController.

import { useEffect, useMemo, useRef, useState } from "react"
import {
  createVoiceController,
  type VoiceController,
  type VoiceStatus,
} from "../services/voiceController"
import type { VoiceLanguage } from "../services/voice"

export function useVoiceController(language: VoiceLanguage = "en-IN") {
  const [status, setStatus] = useState<VoiceStatus>("idle")
  const [interim, setInterim] = useState("")
  const [transcript, setTranscript] = useState("")
  const [error, setError] = useState<string | null>(null)
  const controllerRef = useRef<VoiceController | null>(null)

  const controller = useMemo<VoiceController>(() => {
    if (!controllerRef.current) {
      controllerRef.current = createVoiceController({
        onStatusChange: setStatus,
        onInterim: setInterim,
        onTranscript: setTranscript,
        onError: setError,
      })
    }
    return controllerRef.current
  }, [])

  useEffect(() => {
    controller.setLanguage(language)
  }, [controller, language])

  useEffect(() => {
    const unsubStatus = controller.onStatus(setStatus)
    const unsubInterim = controller.onInterim(setInterim)
    return () => {
      unsubStatus()
      unsubInterim()
    }
  }, [controller])

  return {
    controller,
    status,
    interim,
    transcript,
    error,
    setError,
  }
}
