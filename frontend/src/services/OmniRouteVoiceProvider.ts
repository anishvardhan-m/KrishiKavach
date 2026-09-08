/**
 * OmniRouteVoiceProvider — primary voice provider.
 *
 * STT: records audio → POST to backend → ElevenLabs/OmniRoute transcription.
 * TTS: POST text to backend → ElevenLabs/OmniRoute audio → HTMLAudioElement.
 *
 * Falls back to BrowserVoiceProvider when the backend is unavailable
 * (503, unreachable, or no API key configured).
 */

import type { VoiceLanguage } from "./voice"
import type { VoiceProvider } from "./voice"
import {
  isOmniRouteUnavailable,
  speakToUrl,
  transcribe,
  AutoplayBlocked,
} from "./omniroute"
import type { VoiceConfig } from "./omniroute"
import { useAudioRecorder } from "../hooks/useAudioRecorder"

type RecorderLike = ReturnType<typeof useAudioRecorder>

export interface OmniRouteVoiceProviderDeps {
  getRecorder: () => RecorderLike
  getBrowserProvider: () => VoiceProvider | null
  getConfig: () => VoiceConfig | null
}

export class OmniRouteVoiceProvider implements VoiceProvider {
  private readonly _getRecorder: () => RecorderLike
  private readonly _getBrowser: () => VoiceProvider | null
  private readonly _getConfig: () => VoiceConfig | null

  // ── Interruptible TTS ──────────────────────────────────────────────────
  //
  // KrishiKavach must play ONE voice at a time. Any new speak() request
  // immediately cancels any currently-playing audio and discards any
  // in-flight async TTS request that belongs to an older request.
  //
  // A monotonically increasing token is used so that an older async request
  // that finishes after a newer request has started can detect that it has
  // been superseded and must NOT start playback. This prevents race
  // conditions where two voices overlap.
  private _currentAudio: HTMLAudioElement | null = null
  private _activeToken = 0

  constructor(deps: OmniRouteVoiceProviderDeps) {
    this._getRecorder = deps.getRecorder
    this._getBrowser = deps.getBrowserProvider
    this._getConfig = deps.getConfig
  }

  isSupported(): boolean {
    return typeof MediaRecorder !== "undefined"
  }

  isOmniRouteAvailable(): boolean {
    // Backend STT is available when stt_provider is ElevenLabs or OmniRoute.
    const stt = this._getConfig()?.stt_provider
    return stt === "elevenlabs" || stt === "omniroute"
  }

  onInterim(_handler: (text: string) => void): () => void {
    // Interim transcript is not streamed from the backend in this design.
    return () => {}
  }

  // ── TTS ────────────────────────────────────────────────────────────────

  async speak(text: string, language: VoiceLanguage): Promise<void> {
    // New request: immediately stop any currently-playing audio and claim
    // the token so any in-flight older request discards itself.
    this.cancel()
    const token = this._activeToken

    const cfg = this._getConfig()
    // Use backend TTS when configured (ElevenLabs or OmniRoute).
    const useBackend =
      cfg?.tts_provider === "elevenlabs" || cfg?.tts_provider === "omniroute"
    if (!useBackend) {
      await this._fallbackSpeak(text, language)
      return
    }
    try {
      const url = await speakToUrl(text, language)
      // If a newer speak() started while we were fetching, discard this one.
      if (token !== this._activeToken) return
      await this._play(url, token)
    } catch (e) {
      if (isOmniRouteUnavailable(e)) {
        await this._fallbackSpeak(text, language)
      } else {
        throw e
      }
    }
  }

  private async _fallbackSpeak(text: string, language: VoiceLanguage): Promise<void> {
    const bp = this._getBrowser()
    if (bp) await bp.speak(text, language)
  }

  private _play(url: string, token: number): Promise<void> {
    return new Promise((resolve, reject) => {
      // If this request was already superseded before playback began, do
      // not create a new audio element at all.
      if (token !== this._activeToken) {
        resolve()
        return
      }
      const audio = new Audio(url)
      this._currentAudio = audio
      const cleanup = () => {
        this._currentAudio = null
      }
      audio.onended = () => {
        cleanup()
        resolve()
      }
      audio.onerror = () => {
        cleanup()
        resolve()
      }
      audio.play().catch((err) => {
        cleanup()
        // Detect browser autoplay block → surface as AutoplayBlocked so the
        // UI can prompt the user to tap rather than silently falling back.
        if (err?.name === "NotAllowedError" || err?.name === "AbortError") {
          reject(new AutoplayBlocked())
        } else {
          reject(err)
        }
      })
    })
  }

  cancel(): void {
    // Invalidate the current token so any in-flight async request that
    // resolves afterwards will see it is stale and discard its audio.
    this._activeToken += 1
    if (this._currentAudio) {
      this._currentAudio.pause()
      this._currentAudio = null
    }
    const bp = this._getBrowser()
    if (bp) bp.cancel()
  }

  // ── STT ────────────────────────────────────────────────────────────────

  /**
   * Listen using the configured backend STT provider (ElevenLabs or OmniRoute).
   * Falls back to browser Web Speech API on error.
   */
  async listen(language: VoiceLanguage, timeoutMs = 8000): Promise<string | null> {
    const cfg = this._getConfig()
    const sttProvider = cfg?.stt_provider

    // Use backend STT when ElevenLabs or OmniRoute is configured.
    if (sttProvider === "elevenlabs" || sttProvider === "omniroute") {
      const result = await this._listenBackend(language, timeoutMs)
      if (result !== null) return result
      // Backend returned null — fall through to browser fallback if available.
    }

    // Browser fallback
    const bp = this._getBrowser()
    if (bp) return bp.listen(language, timeoutMs)
    return null
  }

  /**
   * Record audio for up to `timeoutMs` or until silence is detected.
   * POSTs the recording to the backend (which proxies to ElevenLabs/OmniRoute).
   * Returns the transcript or null on silence/error.
   */
  private async _listenBackend(
    language: VoiceLanguage,
    timeoutMs: number,
  ): Promise<string | null> {
    const recorder = this._getRecorder()
    try {
      await recorder.start()
    } catch {
      return null
    }

    // Wait until the recorder leaves "recording" or we time out.
    const blob = await new Promise<Blob | null>((resolve) => {
      const start = Date.now()
      const poll = setInterval(() => {
        if (recorder.state === "idle") {
          clearInterval(poll)
          recorder
            .stop()
            .then((b) => resolve(b))
            .catch(() => resolve(null))
          return
        }
        if (Date.now() - start >= timeoutMs) {
          clearInterval(poll)
          recorder
            .stop()
            .then((b) => resolve(b))
            .catch(() => resolve(null))
        }
      }, 100)
    })

    if (!blob) return null

    try {
      const { text } = await transcribe(blob, language)
      return text || null
    } catch (e) {
      if (isOmniRouteUnavailable(e)) {
        // Try browser fallback
        const bp = this._getBrowser()
        if (bp) return bp.listen(language, timeoutMs)
        return null
      }
      throw e
    }
  }

  recorderError() {
    return this._getRecorder().error
  }
}
