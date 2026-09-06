// Expert help card — explains how the farmer can reach an agronomist.

import type { VoiceLanguage } from "../services/voice"
import { t } from "../i18n/strings"

interface Props {
  language: VoiceLanguage
  onDone: () => void
  onSpeak: () => void
}

export function ExpertCard({ language, onDone, onSpeak }: Props) {
  const listenLabel =
    language === "hi-IN" ? "🔊 सुनें" : language === "mr-IN" ? "🔊 ऐका" : "🔊 Listen"
  const backLabel =
    language === "hi-IN" ? "← वापस" : language === "mr-IN" ? "← मागे" : "← Back"

  return (
    <div className="card" role="region" aria-label="Expert help">
      <h2>{t("action_expert_help", language)}</h2>
      <p>
        {language === "hi-IN"
          ? "एक कृषि विशेषज्ञ आपकी फोटो देखकर बता सकते हैं कि क्या करना है। यह किसानों के लिए मुफ़्त है।"
          : language === "mr-IN"
          ? "एक कृषी तज्ञ तुमचा फोटो पाहून सांगू शकतो काय करावे. हे शेतकऱ्यांसाठी मोफत आहे."
          : "An agriculture expert can look at your photo and tell you what to do. This is free for farmers."}
      </p>
      <div
        style={{
          background: "#f0fdf4",
          border: "1px solid #bbf7d0",
          borderRadius: 12,
          padding: 16,
          marginBottom: 12,
        }}
      >
        <div style={{ fontSize: 16, fontWeight: 600, color: "#14532d" }}>
          📞 {t("krishi_vigyan_kendra", language)}
        </div>
        <div style={{ fontSize: 22, fontWeight: 700, marginTop: 6 }}>
          {t("helpline_number", language)}
        </div>
        <div style={{ fontSize: 13, color: "#475569", marginTop: 4 }}>
          {t("helpline_hours", language)}
        </div>
      </div>
      <div
        style={{
          background: "#fff7ed",
          border: "1px solid #fed7aa",
          borderRadius: 12,
          padding: 16,
          marginBottom: 12,
        }}
      >
        <div style={{ fontSize: 16, fontWeight: 600, color: "#9a3412" }}>
          📸 {language === "hi-IN" ? "आपकी फोटो के लिए" : language === "mr-IN" ? "तुमच्या फोटोसाठी" : "For your photo"}
        </div>
        <p style={{ margin: "6px 0 0", fontSize: 15 }}>
          {t("expert_photo_explainer", language)}
        </p>
      </div>
      <div className="inline-actions">
        <button className="small-btn primary" onClick={onSpeak} type="button">
          {listenLabel}
        </button>
        <button className="small-btn" onClick={onDone} type="button">
          {backLabel}
        </button>
      </div>
    </div>
  )
}
