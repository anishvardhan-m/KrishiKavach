// Voice status banner — shows current state (idle / speaking / listening / processing)
// and any interim transcript while the farmer is speaking.

import type { VoiceStatus } from "../services/voiceController"

interface Props {
  status: VoiceStatus
  interim: string
  message: string
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

export function VoiceBanner({ status, interim, message }: Props) {
  return (
    <div className={`voice-banner ${STATUS_CLASS[status]}`} role="status" aria-live="polite">
      <span className="indicator" />
      <div className="text">
        {message || STATUS_TEXT[status]}
        {status === "listening" && interim && (
          <span className="heard">“{interim}”</span>
        )}
      </div>
    </div>
  )
}
