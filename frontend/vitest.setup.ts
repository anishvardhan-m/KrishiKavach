import { vi } from 'vitest'

// Mock window.speechSynthesis before each test so token state is clean.
beforeEach(() => {
  if (typeof window !== 'undefined') {
    ;(window as any).speechSynthesis = {
      cancel: vi.fn(),
      speak: vi.fn(),
      paused: false,
    }
  }
})