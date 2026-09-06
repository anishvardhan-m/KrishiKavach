// VoiceInteractionController — high-level reusable voice interaction pattern.
// Pattern (per the SIH spec):
//   1. speak an instruction/prompt
//   2. say "Please speak. I am listening."
//   3. listen to the farmer
//   4. interpret the intent
//   5. perform an action and respond
//
// This controller is provider-agnostic. Pass any VoiceProvider
// (currently WebSpeechProvider; Omi can replace it later).

import { getVoiceProvider, type VoiceLanguage, type VoiceProvider } from "./voice"
import type { VoiceIntent } from "../types"

const LISTENING_PROMPTS: Record<VoiceLanguage, string> = {
  "en-IN": "Please speak. I am listening.",
  "hi-IN": "कृपया बोलिए। मैं सुन रहा हूँ।",
  "mr-IN": "कृपया बोला. मी ऐकत आहे.",
}

export type VoiceStatus = "idle" | "speaking" | "listening" | "processing"

export interface VoiceCallbacks {
  onStatusChange?: (status: VoiceStatus) => void
  onInterim?: (text: string) => void
  onTranscript?: (text: string) => void
  onError?: (message: string) => void
}

export interface VoiceController {
  setLanguage(lang: VoiceLanguage): void
  getLanguage(): VoiceLanguage
  /** Speak a prompt and return when finished. */
  speak(text: string): Promise<void>
  /** Standard "Please speak. I am listening." pattern. */
  promptAndListen(): Promise<string | null>
  /** Speak a prompt, then listen, then interpret the intent via backend. */
  promptListenAndInterpret(
    text: string,
  ): Promise<VoiceIntent | null>
  /** Just listen and resolve to raw transcript. */
  listen(): Promise<string | null>
  /** Parse a transcript into a structured intent via backend. */
  interpret(transcript: string): Promise<VoiceIntent | null>
  /** Cancel any speech or recognition. */
  cancel(): void
  /** Subscribe to status changes. */
  onStatus(cb: (status: VoiceStatus) => void): () => void
  /** Subscribe to interim transcript updates. */
  onInterim(cb: (text: string) => void): () => void
  /** Whether speech recognition is supported in this environment. */
  isRecognitionSupported(): boolean
}

const BACKEND_URL = (import.meta as any).env?.VITE_BACKEND_URL || ""

export function createVoiceController(
  callbacks: VoiceCallbacks = {},
  provider?: VoiceProvider,
): VoiceController {
  const p = provider || getVoiceProvider()
  let language: VoiceLanguage = "en-IN"
  let status: VoiceStatus = "idle"
  const statusListeners = new Set<(s: VoiceStatus) => void>()
  const interimListeners = new Set<(t: string) => void>()
  const interimUnsub = p.onInterim((text) => {
    interimListeners.forEach((cb) => cb(text))
  })

  const setStatus = (s: VoiceStatus) => {
    status = s
    callbacks.onStatusChange?.(s)
    statusListeners.forEach((cb) => cb(s))
  }

  return {
    setLanguage(lang) {
      language = lang
    },
    getLanguage() {
      return language
    },

    async speak(text) {
      setStatus("speaking")
      try {
        await p.speak(text, language)
      } finally {
        if (status === "speaking") setStatus("idle")
      }
    },

    async promptAndListen() {
      const prompt = LISTENING_PROMPTS[language] || LISTENING_PROMPTS["en-IN"]
      await p.speak(prompt, language)
      setStatus("listening")
      callbacks.onInterim?.("")
      const result = await p.listen(language)
      if (result) callbacks.onTranscript?.(result)
      setStatus("idle")
      return result
    },

    async promptListenAndInterpret(text) {
      await p.speak(text, language)
      setStatus("listening")
      callbacks.onInterim?.("")
      const transcript = await p.listen(language)
      if (transcript) callbacks.onTranscript?.(transcript)
      setStatus("idle")
      if (!transcript) return null
      setStatus("processing")
      try {
        const intent = await interpret(transcript, language)
        return intent
      } finally {
        setStatus("idle")
      }
    },

    async listen() {
      setStatus("listening")
      callbacks.onInterim?.("")
      const result = await p.listen(language)
      if (result) callbacks.onTranscript?.(result)
      setStatus("idle")
      return result
    },

    async interpret(transcript) {
      return interpret(transcript, language)
    },

    cancel() {
      p.cancel()
      if (status !== "idle") setStatus("idle")
    },

    onStatus(cb) {
      statusListeners.add(cb)
      cb(status)
      return () => statusListeners.delete(cb)
    },

    onInterim(cb) {
      interimListeners.add(cb)
      // Also expose to caller through callbacks.onInterim
      return () => interimListeners.delete(cb)
    },

    isRecognitionSupported() {
      return (p as any).isRecognitionSupported
            ? (p as any).isRecognitionSupported()
            : true
        },
  }
}

async function interpret(
  transcript: string,
  language: VoiceLanguage,
): Promise<VoiceIntent | null> {
  try {
    const res = await fetch(`${BACKEND_URL}/api/voice/parse-intent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transcript, language }),
    })
    if (!res.ok) return null
    const data = (await res.json()) as VoiceIntent
    return data
  } catch (e) {
    console.error("interpret failed", e)
    return null
  }
}

// Cleanup helper for unmount
export function destroyVoiceController(_ctrl: VoiceController) {
  // no-op for now; future providers may need to release resources
  // interimUnsub is held privately — exposed for testing if needed
}
