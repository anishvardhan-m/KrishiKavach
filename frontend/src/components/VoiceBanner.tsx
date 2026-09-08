// Voice status banner — shows current state (idle / speaking / listening / processing)
// and any interim transcript while the farmer is speaking.

import type { ReactNode } from "react"
import type { VoiceStatus } from "../services/voiceController"

interface Props {
  status: VoiceStatus
  interim: string
  message: string
  /** Shown below the message when the browser blocked autoplay on the welcome greeting. */
  autoplayRetry?: ReactNode
}

const STATUS_TEXT: Record<VoiceStatus, string> = {
  idle: "Ready",
  speaking: "Speaking...",
  listening: "Listening...",
  processing: "Thinking...",
  error: "Error",
}

const STATUS_CLASS: Record<VoiceStatus, string> = {
  idle: "",
  speaking: "is-speaking",
  listening: "is-listening",
  processing: "is-speaking",
  error: "is-speaking",
}

export function VoiceBanner({ status, interim, message, autoplayRetry }: Props) {
  return (
    <div className={`voice-banner ${STATUS_CLASS[status]}`} role="status" aria-live="polite">
      <span className="indicator" />
      <div className="text">
        {message || STATUS_TEXT[status]}
        {status === "listening" && interim && (
          <span className="heard">"{interim}"</span>
        )}
      </div>
      {autoplayRetry}
    </div>
  )
}