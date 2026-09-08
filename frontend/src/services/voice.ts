// Voice provider abstraction.
// Current implementation: Web Speech API (browser-native).
// Future providers (e.g. Omi) can be added behind the same interface.

export type VoiceLanguage = "en-IN" | "hi-IN" | "mr-IN"

export interface VoiceProvider {
  /** Whether this provider is usable in the current environment. */
  isSupported(): boolean
  /** Speak the given text in the given language. */
  speak(text: string, language: VoiceLanguage): Promise<void>
  /** Stop any ongoing speech. */
  cancel(): void
  /** Begin listening and resolve with the transcript, or null on silence/timeout. */
  listen(language: VoiceLanguage, timeoutMs?: number): Promise<string | null>
  /** Subscribe to "interim" transcript while listening. */
  onInterim(handler: (text: string) => void): () => void
}

declare global {
  interface Window {
    SpeechRecognition: any
    webkitSpeechRecognition: any
  }
}

/**
 * Web Speech API provider.
 * Uses browser's SpeechSynthesis + SpeechRecognition.
 * Handles environments where recognition is missing (Firefox, Safari iOS < 14.5).
 *
 * Interruptible TTS: a token counter ensures only the latest speak()
 * request's utterance is heard — older in-flight utterances are discarded.
 */
export class WebSpeechProvider implements VoiceProvider {
  private recognition: any | null = null
  private interimHandler: ((text: string) => void) | null = null
  private supportedRecognition!: boolean
  private supportedSynthesis!: boolean
  // Token counter for interruptible TTS. Incremented each time speak()
  // starts. Any in-flight utterance whose onend/onerror fires with a
  // stale token silently discards itself.
  private _activeToken = 0

  isSupported(): boolean {
    return this.supportedSynthesis
  }

  isRecognitionSupported(): boolean {
    return this.supportedRecognition
  }

  onInterim(handler: (text: string) => void): () => void {
    this.interimHandler = handler
    return () => {
      this.interimHandler = null
    }
  }

  speak(text: string, language: VoiceLanguage): Promise<void> {
    return new Promise((resolve) => {
      if (!this.supportedSynthesis) {
        // Silent fallback — UI still shows the text.
        resolve()
        return
      }
      try {
        // New request: cancel any in-flight utterance and claim the token so
        // any older in-flight utterance discards itself on its onend/onerror.
        this._activeToken += 1
        const token = this._activeToken
        window.speechSynthesis.cancel()
        const utter = new SpeechSynthesisUtterance(text)
        utter.lang = language
        utter.rate = 0.95
        utter.pitch = 1
        utter.onend = () => {
          // Only resolve for the latest request; a stale utterance must not
          // unblock the newer one.
          if (token !== this._activeToken) return
          resolve()
        }
        utter.onerror = () => {
          if (token !== this._activeToken) return
          resolve()
        }
        window.speechSynthesis.speak(utter)
      } catch {
        resolve()
      }
    })
  }

  cancel(): void {
    // Invalidate the token so any in-flight utterance's onend/onerror fires
    // with a stale token and discards itself.
    this._activeToken += 1
    if (this.supportedSynthesis) {
      try {
        window.speechSynthesis.cancel()
      } catch {
        /* noop */
      }
    }
    this.stopRecognition()
  }

  listen(language: VoiceLanguage, timeoutMs = 6000): Promise<string | null> {
    return new Promise((resolve) => {
      if (!this.supportedRecognition) {
        resolve(null)
        return
      }
      const SR =
        window.SpeechRecognition || window.webkitSpeechRecognition
      const recognition = new SR()
      recognition.lang = language
      recognition.interimResults = true
      recognition.maxAlternatives = 1
      recognition.continuous = false

      let finalTranscript = ""
      let resolved = false
      let timeoutId: number | null = null

      const finish = (value: string | null) => {
        if (resolved) return
        resolved = true
        if (timeoutId !== null) window.clearTimeout(timeoutId)
        try {
          recognition.stop()
        } catch {
          /* noop */
        }
        this.recognition = null
        resolve(value)
      }

      recognition.onresult = (event: any) => {
        let interim = ""
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const res = event.results[i]
          if (res.isFinal) {
            finalTranscript += res[0].transcript
          } else {
            interim += res[0].transcript
          }
        }
        if (this.interimHandler) {
          this.interimHandler(interim || finalTranscript)
        }
      }

      recognition.onerror = (e: any) => {
        if (e?.error === "no-speech" || e?.error === "aborted") {
          finish(null)
        } else {
          finish(null)
        }
      }

      recognition.onend = () => {
        finish(finalTranscript.trim() || null)
      }

      try {
        recognition.start()
        this.recognition = recognition
      } catch {
        finish(null)
        return
      }

      timeoutId = window.setTimeout(() => finish(null), timeoutMs)
    })
  }

  private stopRecognition() {
    if (this.recognition) {
      try {
        this.recognition.stop()
      } catch {
        /* noop */
      }
      this.recognition = null
    }
  }
}

let providerInstance: VoiceProvider | null = null

export function getVoiceProvider(): VoiceProvider {
  if (!providerInstance) {
    providerInstance = new WebSpeechProvider()
  }
  return providerInstance
}
