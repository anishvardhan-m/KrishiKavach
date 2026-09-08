import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// ── OmniRouteVoiceProvider tests ──────────────────────────────────────
describe('OmniRouteVoiceProvider — interruptible TTS', () => {
  let AudioInstances: any[] = []

  beforeEach(() => {
    AudioInstances = []
    // @ts-ignore — mock Audio constructor for the test environment
    ;(globalThis as any).Audio = class MockAudio {
      src: string = ''
      onended: ((...args: any[]) => void) | null = null
      onerror: ((...args: any[]) => void) | null = null
      pause() {}
      play() {
        return Promise.resolve()
      }
      constructor(src: string) {
        this.src = src
        AudioInstances.push(this)
      }
    }
  })

  afterEach(() => {
    // @ts-ignore
    delete (globalThis as any).Audio
  })

  it('creates a single Audio element on speak()', async () => {
    const { OmniRouteVoiceProvider } = await import('../OmniRouteVoiceProvider')
    const provider = new OmniRouteVoiceProvider({
      getRecorder: () => null as any,
      getBrowserProvider: () => null,
      getConfig: () => ({
        provider: 'elevenlabs',
        stt_provider: 'elevenlabs',
        tts_provider: 'elevenlabs',
        default_language: 'hi-IN',
        stt_model: null,
        tts_model: null,
        tts_voice: null,
        elevenlabs_stt_model: null,
        elevenlabs_voice_id: null,
        elevenlabs_model_id: null,
        browser_fallback_supported: true,
      }),
    })

    const speakToUrl = (await import('../omniroute')).speakToUrl
    vi.mocked(speakToUrl).mockResolvedValueOnce('data:audio/mpeg;base64,AAA')

    await provider.speak('hello', 'hi-IN')

    expect(AudioInstances.length).toBe(1)
    expect(AudioInstances[0].src).toBe('data:audio/mpeg;base64,AAA')
  })

  it('discards an older in-flight request when a newer one starts', async () => {
    const { OmniRouteVoiceProvider } = await import('../OmniRouteVoiceProvider')
    const provider = new OmniRouteVoiceProvider({
      getRecorder: () => null as any,
      getBrowserProvider: () => null,
      getConfig: () => ({
        provider: 'elevenlabs',
        stt_provider: 'elevenlabs',
        tts_provider: 'elevenlabs',
        default_language: 'hi-IN',
        stt_model: null,
        tts_model: null,
        tts_voice: null,
        elevenlabs_stt_model: null,
        elevenlabs_voice_id: null,
        elevenlabs_model_id: null,
        browser_fallback_supported: true,
      }),
    })

    const speakToUrl = (await import('../omniroute')).speakToUrl
    // First request resolves after a delay
    const firstPromise = new Promise<string>((r) => {
      setTimeout(() => r('data:audio/mpeg;base64,OLD'), 100)
    })
    vi.mocked(speakToUrl).mockImplementationOnce(() => firstPromise)
    vi.mocked(speakToUrl).mockResolvedValueOnce('data:audio/mpeg;base64,NEW')

    // Start first speak
    const p1 = provider.speak('old', 'hi-IN')
    // Wait for the mock to be called
    await new Promise((r) => setTimeout(r, 10))
    // Start second speak while first is still in-flight
    const p2 = provider.speak('new', 'hi-IN')
    // Wait for both to finish
    await Promise.all([p1, p2])

    // Only the NEW audio should have been created
    expect(AudioInstances.length).toBe(1)
    expect(AudioInstances[0].src).toBe('data:audio/mpeg;base64,NEW')
  })

  it('cancel() invalidates the token so older requests discard their audio', async () => {
    const { OmniRouteVoiceProvider } = await import('../OmniRouteVoiceProvider')
    const provider = new OmniRouteVoiceProvider({
      getRecorder: () => null as any,
      getBrowserProvider: () => null,
      getConfig: () => ({
        provider: 'elevenlabs',
        stt_provider: 'elevenlabs',
        tts_provider: 'elevenlabs',
        default_language: 'hi-IN',
        stt_model: null,
        tts_model: null,
        tts_voice: null,
        elevenlabs_stt_model: null,
        elevenlabs_voice_id: null,
        elevenlabs_model_id: null,
        browser_fallback_supported: true,
      }),
    })

    const speakToUrl = (await import('../omniroute')).speakToUrl
    vi.mocked(speakToUrl).mockResolvedValueOnce('data:audio/mpeg;base64,OLD')

    const p1 = provider.speak('old', 'hi-IN')
    // Immediately cancel — the old request's token should be invalidated
    provider.cancel()

    // Wait for any async operations to settle
    await Promise.resolve()

    // The cancelled request should not have created an Audio element
    // because cancel() increments _activeToken, making the first request's token stale
    expect(AudioInstances.length).toBe(0)
  })
})

// ── WebSpeechProvider tests ───────────────────────────────────────────
describe('WebSpeechProvider — interruptible TTS', () => {
  beforeEach(() => {
    if (typeof window !== 'undefined') {
      ;(window as any).speechSynthesis = {
        cancel: vi.fn(),
        speak: vi.fn(),
        paused: false,
      }
    }
  })

  afterEach(() => {
    if (typeof window !== 'undefined') {
      ;(window as any).speechSynthesis = {
        cancel: () => {},
        speak: () => {},
        paused: false,
      }
    }
  })

  it('creates an utterance on speak()', async () => {
    const { WebSpeechProvider } = await import('../voice')
    const provider = new WebSpeechProvider()

    await provider.speak('hello', 'hi-IN')

    const callCount = (window as any).speechSynthesis.speak.mock.calls.length
    expect(callCount).toBe(1)
  })

  it('only the latest utterance resolves its promise when speak() is called twice', async () => {
    const { WebSpeechProvider } = await import('../voice')
    const provider = new WebSpeechProvider()

    const p1 = provider.speak('old', 'hi-IN')
    const p2 = provider.speak('new', 'hi-IN')

    // Trigger the first utterance's onend — should NOT resolve p1
    let p1Resolved = false
    p1.then(() => { p1Resolved = true })
    const firstUtterance = (window as any).speechSynthesis.speak.mock.calls[0][0]
    firstUtterance.onend()
    await Promise.resolve()
    expect(p1Resolved).toBe(false)

    // Trigger the second utterance's onend — should resolve p2
    let p2Resolved = false
    p2.then(() => { p2Resolved = true })
    const secondUtterance = (window as any).speechSynthesis.speak.mock.calls[1][0]
    secondUtterance.onend()
    await Promise.resolve()
    expect(p2Resolved).toBe(true)
  })

  it('cancel() invalidates the token so stale utterances discard themselves', async () => {
    const { WebSpeechProvider } = await import('../voice')
    const provider = new WebSpeechProvider()

    const p1 = provider.speak('hello', 'hi-IN')
    provider.cancel()

    // Trigger the utterance's onend — should NOT resolve p1
    let p1Resolved = false
    p1.then(() => { p1Resolved = true })
    const firstUtterance = (window as any).speechSynthesis.speak.mock.calls[0][0]
    firstUtterance.onend()
    await Promise.resolve()
    expect(p1Resolved).toBe(false)
  })
})