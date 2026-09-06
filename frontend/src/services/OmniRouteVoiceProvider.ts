/**
 * OmniRouteVoiceProvider — primary voice provider.
 *
 * STT: records audio → POST to backend → OmniRoute transcription.
 * TTS: POST text to backend → OmniRoute audio → HTMLAudioElement.
 *
 * Falls back to BrowserVoiceProvider when OmniRoute is unavailable
 * (503, unreachable, or no API key configured).
 */

import type { VoiceLanguage } from "./voice"
import type { VoiceProvider } from "./voice"
import {
  isOmniRouteUnavailable,
  speakToUrl,
  transcribe,
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

  private _currentAudio: HTMLAudioElement | null = null

  constructor(deps: OmniRouteVoiceProviderDeps) {
    this._getRecorder = deps.getRecorder
    this._getBrowser = deps.getBrowserProvider
    this._getConfig = deps.getConfig
  }

  isSupported(): boolean {
    return typeof MediaRecorder !== "undefined"
  }

  isOmniRouteAvailable(): boolean {
    return this._getConfig()?.provider === "omniroute"
  }

  onInterim(_handler: (text: string) => void): () => void {
    // Interim transcript is not streamed from OmniRoute in this design.
    return () => {}
  }

  // ── TTS ────────────────────────────────────────────────────────────────

  async speak(text: string, language: VoiceLanguage): Promise<void> {
    this.cancel()
    const cfg = this._getConfig()
    if (cfg?.provider !== "omniroute") {
      await this._fallbackSpeak(text, language)
      return
    }
    try {
      const url = await speakToUrl(text, language)
      await this._play(url)
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

  private _play(url: string): Promise<void> {
    return new Promise((resolve) => {
      const audio = new Audio(url)
      this._currentAudio = audio
      const done = () => {
        this._currentAudio = null
        resolve()
      }
      audio.onended = done
      audio.onerror = done
      audio.play().catch(() => {
        this._currentAudio = null
        resolve()
      })
    })
  }

  cancel(): void {
    if (this._currentAudio) {
      this._currentAudio.pause()
      this._currentAudio = null
    }
    const bp = this._getBrowser()
    if (bp) bp.cancel()
  }

  // ── STT ────────────────────────────────────────────────────────────────

  async listen(language: VoiceLanguage, timeoutMs = 8000): Promise<string | null> {
    const cfg = this._getConfig()

    if (cfg?.provider === "omniroute") {
      const result = await this._listenOmniRoute(language, timeoutMs)
      // If the recording yielded no audio, return null (caller handles it)
      if (result === null && !this._getRecorder().error) {
        return null
      }
      if (result) return result
    }

    // Fallback to browser speech recognition
    const bp = this._getBrowser()
    if (bp) return bp.listen(language, timeoutMs)
    return null
  }

  /**
   * Record audio for up to `timeoutMs` or until the user calls `recorder.stop()`.
   * Returns the resulting Blob or null on silence/error.
   *
   * The controller wires `recorder.stop()` to the action button or to silence.
   * For now, we just wait for either the timeout or an explicit stop signal
   * by polling the recorder state.
   */
  private async _listenOmniRoute(
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
          // We must ask the hook to flush; the hook accumulates the blob on stop().
          // Use the public stop() to finalize.
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
