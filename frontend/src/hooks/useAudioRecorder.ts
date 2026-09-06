/**
 * useAudioRecorder — browser MediaRecorder hook.
 * Records microphone input and resolves to a Blob of audio/webm.
 * Handles permission denial and unsupported browsers gracefully.
 */
import { useCallback, useRef, useState } from "react"

export type RecorderState = "idle" | "recording" | "stopping" | "error"

export interface RecorderError {
  kind:
    | "permission-denied"
    | "not-supported"
    | "stream-failed"
    | "encoding-failed"
    | "unknown"
  message: string
}

interface UseAudioRecorderReturn {
  state: RecorderState
  error: RecorderError | null
  /** Start recording. Resolves when MediaRecorder is ready. */
  start: () => Promise<void>
  /** Stop recording. Resolves with the audio Blob when encoding is complete. */
  stop: () => Promise<Blob | null>
  /** Discard the current recording without returning it. */
  cancel: () => void
}

export function useAudioRecorder(): UseAudioRecorderReturn {
  const [state, setState] = useState<RecorderState>("idle")
  const [error, setError] = useState<RecorderError | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const resolveStopRef = useRef<((b: Blob | null) => void) | null>(null)

  const cancel = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current = null
    }
    chunksRef.current = []
    resolveStopRef.current = null
    setState("idle")
  }, [])

  const start = useCallback(async (): Promise<void> => {
    cancel()
    setError(null)

    if (!navigator.mediaDevices?.getUserMedia) {
      const err: RecorderError = {
        kind: "not-supported",
        message: "Recording is not supported in this browser.",
      }
      setError(err)
      setState("error")
      return
    }

    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (e: any) {
      const kind: RecorderError["kind"] =
        e?.name === "NotAllowedError" ||
        e?.name === "PermissionDeniedError"
          ? "permission-denied"
          : "stream-failed"
      const err: RecorderError = {
        kind,
        message:
          kind === "permission-denied"
            ? "Microphone access was denied. Please allow microphone access and try again."
            : `Could not access microphone: ${e?.message ?? "unknown error"}`,
      }
      setError(err)
      setState("error")
      return
    }

    streamRef.current = stream

    // Prefer webm; fall back to whatever the browser gives us.
    const mimeType =
      MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "audio/mp4"

    let recorder: MediaRecorder
    try {
      recorder = new MediaRecorder(stream, { mimeType })
    } catch (e: any) {
      const err: RecorderError = {
        kind: "encoding-failed",
        message: `Could not create audio recorder: ${e?.message ?? "unknown error"}`,
      }
      setError(err)
      setState("error")
      return
    }

    mediaRecorderRef.current = recorder
    chunksRef.current = []

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) {
        chunksRef.current.push(e.data)
      }
    }

    recorder.onstop = () => {
      const mimeType2 = recorder.mimeType || "audio/webm"
      const blob =
        chunksRef.current.length > 0
          ? new Blob(chunksRef.current, { type: mimeType2 })
          : null
      chunksRef.current = []
      stream.getTracks().forEach((t) => t.stop())
      streamRef.current = null
      mediaRecorderRef.current = null
      setState("idle")
      resolveStopRef.current?.(blob)
      resolveStopRef.current = null
    }

    recorder.onerror = () => {
      const err: RecorderError = {
        kind: "encoding-failed",
        message: "An error occurred while recording audio.",
      }
      setError(err)
      setState("error")
      resolveStopRef.current?.(null)
      resolveStopRef.current = null
    }

    recorder.start(100) // collect chunks every 100ms
    setState("recording")
  }, [cancel])

  const stop = useCallback((): Promise<Blob | null> => {
    return new Promise((resolve) => {
      if (state !== "recording" || !mediaRecorderRef.current) {
        resolve(null)
        return
      }
      resolveStopRef.current = resolve
      setState("stopping")
      mediaRecorderRef.current.stop()
    })
  }, [state])

  return { state, error, start, stop, cancel }
}
