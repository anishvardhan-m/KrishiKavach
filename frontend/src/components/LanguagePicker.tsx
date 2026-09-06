// Language picker — lets the farmer switch between supported languages.

import type { VoiceLanguage } from "../services/voice"
import { t } from "../i18n/strings"

const LANGUAGES: { code: VoiceLanguage; label: string }[] = [
  { code: "hi-IN", label: "हिन्दी" },
  { code: "mr-IN", label: "मराठी" },
  { code: "en-IN", label: "English" },
]

interface Props {
  current: VoiceLanguage
  onChange: (lang: VoiceLanguage) => void
}

export function LanguagePicker({ current, onChange }: Props) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        fontSize: 13,
      }}
      role="group"
      aria-label={t("language_label", current)}
    >
      {LANGUAGES.map(({ code, label }) => (
        <button
          key={code}
          type="button"
          onClick={() => onChange(code)}
          style={{
            appearance: "none",
            background: code === current ? "#16a34a" : "#ffffff",
            color: code === current ? "#ffffff" : "#374151",
            border: "1px solid",
            borderColor: code === current ? "#16a34a" : "#d1d5db",
            borderRadius: 999,
            padding: "4px 10px",
            fontSize: 13,
            fontWeight: 600,
            cursor: "pointer",
          }}
          aria-pressed={code === current}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
