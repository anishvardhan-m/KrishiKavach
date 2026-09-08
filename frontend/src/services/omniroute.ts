/**
 * OmniRoute voice provider for the frontend.
 *
 * Records audio in the browser, sends it to the backend (which proxies to
 * OmniRoute), and plays back TTS audio from the backend.
 *
 * Architecture:
 *   Frontend (this) → backend /api/voice/transcribe → OmniRoute STT
 *   Frontend (this) → backend /api/voice/speak   → OmniRoute TTS
 *
 * The API key lives ONLY in the backend environment — it is never exposed
 * to the browser.
 *
 * Falls back to BrowserVoiceProvider when OmniRoute is unavailable.
 */

import type { VoiceLanguage } from "./voice"
import type { RecorderError } from "../hooks/useAudioRecorder"

// ---------------------------------------------------------------------------
// Backend API client (voice endpoints only)
// ---------------------------------------------------------------------------

export interface VoiceConfig {
  provider: string
  stt_provider: string
  tts_provider: string
  default_language: string
  stt_model: string | null
  tts_model: string | null
  tts_voice: string | null
  elevenlabs_stt_model: string | null
  elevenlabs_voice_id: string | null
  elevenlabs_model_id: string | null
  browser_fallback_supported: boolean
}

interface TranscribeResult {
  text: string
  language: string
  provider: string
  confidence: number | null
}

export async function fetchVoiceConfig(): Promise<VoiceConfig> {
  const res = await fetch("/api/voice/config")
  if (!res.ok) throw new Error(`Voice config failed: ${res.status}`)
  return res.json() as Promise<VoiceConfig>
}

export async function transcribe(
  audioBlob: Blob,
  language: VoiceLanguage,
): Promise<TranscribeResult> {
  const form = new FormData()
  form.append("file", audioBlob, "recording.webm")
  form.append("language", language)
  const res = await fetch("/api/voice/transcribe", {
    method: "POST",
    body: form,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    throw new OmniRouteUnavailable(
      `Transcribe failed (${res.status}): ${body}`,
    )
  }
  return res.json() as Promise<TranscribeResult>
}

export async function speakToUrl(
  text: string,
  language: VoiceLanguage,
  voice?: string,
): Promise<string> {
  // Returns a data: URL (base64 audio) that can be played immediately.
  const body = { text, language, voice }
  const res = await fetch("/api/voice/speak", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const msg = await res.text().catch(() => "")
    throw new OmniRouteUnavailable(`Speak failed (${res.status}): ${msg}`)
  }
  const arrayBuffer = await res.arrayBuffer()
  const mime = res.headers.get("Content-Type") || "audio/mpeg"
  const b64 = btoa(
    new Uint8Array(arrayBuffer).reduce(
      (data, byte) => data + String.fromCharCode(byte),
      "",
    ),
  )
  return `data:${mime};base64,${b64}`
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

export class OmniRouteUnavailable extends Error {
  constructor(message: string) {
    super(message)
    this.name = "OmniRouteUnavailable"
  }
}

export function isOmniRouteUnavailable(e: unknown): boolean {
  return e instanceof OmniRouteUnavailable
}

/**
 * Thrown when browser autoplay policy blocks audio (e.g. user hasn't tapped
 * yet). Distinct from "service is unavailable" so the UI can prompt the user
 * to retry on first interaction rather than falling back silently.
 */
export class AutoplayBlocked extends Error {
  constructor() {
    super("Browser autoplay blocked the audio playback")
    this.name = "AutoplayBlocked"
  }
}

export function isAutoplayBlocked(e: unknown): boolean {
  return e instanceof AutoplayBlocked
}

// ---------------------------------------------------------------------------
// Provider interface (matches VoiceProvider in voice.ts)
// ---------------------------------------------------------------------------

export interface OmniRouteProvider {
  isSupported(): boolean
  speak(text: string, language: VoiceLanguage): Promise<void>
  cancel(): void
  listen(
    language: VoiceLanguage,
    timeoutMs?: number,
  ): Promise<string | null>
  onInterim(handler: (text: string) => void): () => void
  /** Check if OmniRoute is reachable right now. */
  isOmniRouteAvailable(): Promise<boolean>
  /** Last recorder error, if any. */
  recorderError(): RecorderError | null
}
