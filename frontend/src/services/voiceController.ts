// VoiceInteractionController — high-level reusable voice interaction pattern.
// Pattern (per the SIH spec):
//   1. speak an instruction/prompt
//   2. say "Please speak. I am listening."
//   3. listen to the farmer
//   4. interpret the intent
//   5. perform an action and respond
//
// Provider architecture:
//   - OmniRouteVoiceProvider (primary): records audio, sends to backend,
//     backend calls ElevenLabs (STT + TTS) or OmniRoute. API key is never exposed.
//   - WebSpeechProvider (fallback): browser Web Speech API.
//
// The active provider is chosen based on the backend's /api/voice/config:
//   if stt_provider or tts_provider is "elevenlabs" or "omniroute"
//     → backend (with browser fallback inside)
//   else → browser fallback

import { fetchVoiceConfig, isOmniRouteUnavailable, isAutoplayBlocked, type VoiceConfig } from "./omniroute"
import { OmniRouteVoiceProvider } from "./OmniRouteVoiceProvider"
import {
  getVoiceProvider,
  type VoiceLanguage,
  type VoiceProvider,
} from "./voice"
import type { VoiceIntent } from "../types"
import type { useAudioRecorder } from "../hooks/useAudioRecorder"

type RecorderLike = ReturnType<typeof useAudioRecorder>

const BACKEND_URL = (import.meta as any).env?.VITE_BACKEND_URL || ""

const LISTENING_PROMPTS: Record<VoiceLanguage, string> = {
  "en-IN": "Please speak. I am listening.",
  "hi-IN": "कृपया बोलिए। मैं सुन रहा हूँ।",
  "mr-IN": "कृपया बोला. मी ऐकत आहे.",
}

export type VoiceStatus =
  | "idle"
  | "speaking"
  | "listening"
  | "processing"
  | "error"

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
  promptListenAndInterpret(text: string): Promise<VoiceIntent | null>
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
  /** Whether STT is supported (any provider). */
  isRecognitionSupported(): boolean
  /** Which provider is currently active. */
  getActiveProvider(): "omniroute" | "browser" | "none"
  /** Get the loaded voice config (after loadConfig has run). */
  getConfig(): VoiceConfig | null
  /** Last error message, if any. */
  getLastError(): string | null
  /** Whether the last error was an autoplay block (browser policy). */
  isAutoplayBlocked(): boolean
  /** Clear last error. */
  clearError(): void
}

export interface CreateVoiceControllerDeps {
  getRecorder?: () => RecorderLike
}

export function createVoiceController(
  callbacks: VoiceCallbacks = {},
  deps: CreateVoiceControllerDeps = {},
): VoiceController {
  let language: VoiceLanguage = "hi-IN"
  let status: VoiceStatus = "idle"
  let lastError: string | null = null
  let lastErrorAutoplay = false
  const statusListeners = new Set<(s: VoiceStatus) => void>()
  const interimListeners = new Set<(t: string) => void>()

  // Cached config from backend
  let config: VoiceConfig | null = null
  let configLoaded = false

  // Providers
  const browserProvider: VoiceProvider = getVoiceProvider()
  // omniProvider handles STT (via backend /api/voice/transcribe which routes to
  // ElevenLabs or OmniRoute) and TTS (via backend /api/voice/speak which routes
  // to ElevenLabs or OmniRoute depending on VOICE_TTS_PROVIDER).
  const omniProvider: OmniRouteVoiceProvider = new OmniRouteVoiceProvider({
    getRecorder:
      deps.getRecorder ??
      (() => {
        throw new Error(
          "useAudioRecorder() not wired — pass deps.getRecorder from the component.",
        )
      }),
    getBrowserProvider: () => browserProvider,
    getConfig: () => config,
  })

  const setStatus = (s: VoiceStatus) => {
    status = s
    callbacks.onStatusChange?.(s)
    statusListeners.forEach((cb) => cb(s))
  }

  const setError = (msg: string, autoplayBlocked = false) => {
    lastError = msg
    lastErrorAutoplay = autoplayBlocked
    callbacks.onError?.(msg)
  }

  const loadConfig = async (): Promise<void> => {
    if (configLoaded) return
    try {
      config = await fetchVoiceConfig()
      configLoaded = true
    } catch (e) {
      // Backend unreachable; use browser fallback
      config = {
        provider: "browser",
        stt_provider: "browser",
        tts_provider: "browser",
        default_language: "hi-IN",
        stt_model: null,
        tts_model: null,
        tts_voice: null,
        elevenlabs_stt_model: null,
        elevenlabs_voice_id: null,
        elevenlabs_model_id: null,
        browser_fallback_supported: true,
      }
      configLoaded = true
    }
  }

  // Determine which provider is "active" given the loaded config.
  // Backend STT is available when stt_provider is ElevenLabs or OmniRoute.
  // Backend TTS is available when tts_provider is ElevenLabs or OmniRoute.
  // The frontend uses the same /api/voice/speak endpoint for all backend TTS.
  const activeProvider = (): "omniroute" | "browser" | "none" => {
    const sttBackend =
      config?.stt_provider === "elevenlabs" || config?.stt_provider === "omniroute"
    const ttsBackend =
      config?.tts_provider === "elevenlabs" || config?.tts_provider === "omniroute"
    if ((sttBackend || ttsBackend) && omniProvider.isSupported()) {
      return "omniroute"
    }
    if (browserProvider.isSupported()) return "browser"
    return "none"
  }

  // The provider actually used for STT/TTS (backend with internal browser fallback,
  // or browser if the backend is disabled).
  const getProvider = (): VoiceProvider | null => {
    const sttBackend =
      config?.stt_provider === "elevenlabs" || config?.stt_provider === "omniroute"
    const ttsBackend =
      config?.tts_provider === "elevenlabs" || config?.tts_provider === "omniroute"
    if ((sttBackend || ttsBackend) && omniProvider.isSupported()) {
      return omniProvider
    }
    if (browserProvider.isSupported()) return browserProvider
    return null
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
        await loadConfig()
        const p = getProvider()
        if (!p) {
          // No TTS available; still set status to idle.
          return
        }
        await p.speak(text, language)
      } catch (e) {
        if (isAutoplayBlocked(e)) {
          // Browser autoplay blocked — tell App to show the retry button.
          setError("Browser autoplay blocked. Tap the button to hear the message.", true)
        } else if (isOmniRouteUnavailable(e)) {
          // Already handled inside the provider; nothing more to do.
        } else {
          setError((e as Error).message || "Speech synthesis failed", false)
        }
      } finally {
        if (status === "speaking") setStatus("idle")
      }
    },

    async promptAndListen() {
      await loadConfig()
      const prompt = LISTENING_PROMPTS[language] || LISTENING_PROMPTS["en-IN"]
      setStatus("speaking")
      const p = getProvider()
      if (p) {
        try {
          await p.speak(prompt, language)
        } catch {
          /* ignore — we still try to listen */
        }
      }
      if (status === "speaking") setStatus("idle")

      setStatus("listening")
      callbacks.onInterim?.("")
      let result: string | null = null
      try {
        const provider = getProvider()
        if (provider) {
          result = await provider.listen(language)
        }
      } catch (e) {
        if (!isOmniRouteUnavailable(e)) {
          setError((e as Error).message || "Listening failed")
        }
        result = null
      }
      if (result) callbacks.onTranscript?.(result)
      setStatus("idle")
      return result
    },

    async promptListenAndInterpret(text) {
      await loadConfig()
      setStatus("speaking")
      const p = getProvider()
      if (p) {
        try {
          await p.speak(text, language)
        } catch {
          /* ignore */
        }
      }
      if (status === "speaking") setStatus("idle")

      setStatus("listening")
      callbacks.onInterim?.("")
      let transcript: string | null = null
      try {
        const provider = getProvider()
        if (provider) transcript = await provider.listen(language)
      } catch (e) {
        if (!isOmniRouteUnavailable(e)) {
          setError((e as Error).message || "Listening failed")
        }
        transcript = null
      }
      if (transcript) callbacks.onTranscript?.(transcript)
      setStatus("idle")
      if (!transcript) return null
      setStatus("processing")
      try {
        return await interpret(transcript, language)
      } finally {
        setStatus("idle")
      }
    },

    async listen() {
      await loadConfig()
      setStatus("listening")
      callbacks.onInterim?.("")
      let result: string | null = null
      try {
        const provider = getProvider()
        if (provider) result = await provider.listen(language)
      } catch (e) {
        if (!isOmniRouteUnavailable(e)) {
          setError((e as Error).message || "Listening failed")
        }
        result = null
      }
      if (result) callbacks.onTranscript?.(result)
      setStatus("idle")
      return result
    },

    async interpret(transcript) {
      return interpret(transcript, language)
    },

    cancel() {
      const p = getProvider()
      if (p) p.cancel()
      if (status !== "idle") setStatus("idle")
    },

    onStatus(cb) {
      statusListeners.add(cb)
      cb(status)
      return () => statusListeners.delete(cb)
    },

    onInterim(cb) {
      interimListeners.add(cb)
      return () => interimListeners.delete(cb)
    },

    isRecognitionSupported() {
      return omniProvider.isSupported() || browserProvider.isSupported()
    },

    getActiveProvider() {
      return activeProvider()
    },

    getConfig() {
      return config
    },

    getLastError() {
      return lastError
    },

    isAutoplayBlocked() {
      return lastErrorAutoplay
    },

    clearError() {
      lastError = null
      lastErrorAutoplay = false
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
