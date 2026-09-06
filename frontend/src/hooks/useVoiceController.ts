// React hook wrapping the imperative VoiceInteractionController.

import { useEffect, useMemo, useRef, useState } from "react"
import {
  createVoiceController,
  type VoiceController,
  type VoiceStatus,
} from "../services/voiceController"
import { useAudioRecorder } from "./useAudioRecorder"
import type { VoiceLanguage } from "../services/voice"

export function useVoiceController(language: VoiceLanguage = "hi-IN") {
  const [status, setStatus] = useState<VoiceStatus>("idle")
  const [interim, setInterim] = useState("")
  const [transcript, setTranscript] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [activeProvider, setActiveProvider] = useState<
    "omniroute" | "browser" | "none"
  >("none")
  const controllerRef = useRef<VoiceController | null>(null)

  // The recorder instance is shared with the controller via a ref.
  const recorder = useAudioRecorder()

  const controller = useMemo<VoiceController>(() => {
    if (!controllerRef.current) {
      controllerRef.current = createVoiceController(
        {
          onStatusChange: setStatus,
          onInterim: setInterim,
          onTranscript: setTranscript,
          onError: setError,
        },
        {
          getRecorder: () => recorder,
        },
      )
    }
    return controllerRef.current
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  // Refresh active provider after each render (cheap).
  useEffect(() => {
    setActiveProvider(controller.getActiveProvider())
  })

  return {
    controller,
    status,
    interim,
    transcript,
    error,
    setError,
    activeProvider,
    recorder,
  }
}
