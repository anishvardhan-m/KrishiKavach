// Risk card — shows nearby disease outbreak information for the farmer's area.

import type { DiseaseReport } from "../types"
import type { VoiceLanguage } from "../services/voice"
import { t } from "../i18n/strings"

interface Props {
  reports: DiseaseReport[]
  loading: boolean
  error: string | null
  language: VoiceLanguage
  onDone: () => void
  onSpeak: () => void
}

const RISK_CLASS: Record<string, string> = {
  low: "severity-low",
  medium: "severity-medium",
  high: "severity-high",
  critical: "severity-high",
}

const RISK_TEXT: Record<VoiceLanguage, Record<string, string>> = {
  "hi-IN": {
    low: "कम जोखिम",
    medium: "मध्यम जोखिम",
    high: "उच्च जोखिम",
    critical: "गंभीर",
  },
  "mr-IN": {
    low: "कमी धोका",
    medium: "मध्यम धोका",
    high: "जास्त धोका",
    critical: "गंभीर",
  },
  "en-IN": {
    low: "Low risk",
    medium: "Moderate risk",
    high: "High risk",
    critical: "Critical",
  },
}

const BACK_BTN: Record<VoiceLanguage, string> = {
  "hi-IN": "← वापस",
  "mr-IN": "← मागे",
  "en-IN": "← Back",
}

const LISTEN_BTN: Record<VoiceLanguage, string> = {
  "hi-IN": "🔊 सुनें",
  "mr-IN": "🔊 ऐका",
  "en-IN": "🔊 Listen",
}

export function RiskCard({ reports, loading, error, language, onDone, onSpeak }: Props) {
  if (loading) {
    return (
      <div className="card">
        <div className="loading">
          <div className="spinner" />
          {t("loading_outbreaks", language)}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="card">
        <h2>{language === "hi-IN" ? "आस-पास का खतरा" : language === "mr-IN" ? "जवळचा धोका" : "Nearby risk"}</h2>
        <div className="error">{error}</div>
        <div className="inline-actions">
          <button className="small-btn" onClick={onDone} type="button">
            {BACK_BTN[language]}
          </button>
        </div>
      </div>
    )
  }

  if (reports.length === 0) {
    return (
      <div className="card">
        <h2>{language === "hi-IN" ? "आस-पास का खतरा" : language === "mr-IN" ? "जवळचा धोका" : "Nearby risk"}</h2>
        <p>{t("no_outbreaks_explainer", language)}</p>
        <div className="inline-actions">
          <button className="small-btn primary" onClick={onSpeak} type="button">
            {LISTEN_BTN[language]}
          </button>
          <button className="small-btn" onClick={onDone} type="button">
            {BACK_BTN[language]}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="card" role="region" aria-label="Nearby risk">
      <h2>{language === "hi-IN" ? "आस-पास का खतरा" : language === "mr-IN" ? "जवळचा धोका" : "Nearby risk"}</h2>
      <p style={{ color: "#475569", fontSize: 15 }}>
        {language === "hi-IN"
          ? `${reports.length} सक्रिय रोग रिपोर्ट आपके क्षेत्र में:`
          : language === "mr-IN"
          ? `${reports.length} सक्रिय रोग अहवाल तुमच्या भागात:`
          : `${reports.length} active outbreak report${reports.length === 1 ? "" : "s"} in your region:`}
      </p>
      {reports.map((r) => {
        const cls = RISK_CLASS[r.risk_level || "medium"] || "severity-medium"
        const lbl = RISK_TEXT[language]?.[r.risk_level || "medium"] || r.risk_level
        return (
          <div
            key={r.id}
            style={{
              border: "1px solid #e5e7eb",
              borderRadius: 12,
              padding: 12,
              marginBottom: 10,
            }}
          >
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 6 }}>
              <span className={`tag ${cls}`}>{lbl}</span>
              {r.district && <span className="tag">{r.district}</span>}
              {r.crop_type && <span className="tag">{r.crop_type}</span>}
            </div>
            <div style={{ fontWeight: 600, fontSize: 16 }}>
              {r.disease_type || (language === "hi-IN" ? "अज्ञात रोग" : "Unknown disease")}
            </div>
            <div style={{ fontSize: 13, color: "#6b7280", marginTop: 4 }}>
              {language === "hi-IN"
                ? `${r.affected_farms} खेत प्रभावित · ${r.total_cases_reported} मामले दर्ज`
                : `${r.affected_farms} farm${r.affected_farms === 1 ? "" : "s"} affected · ${r.total_cases_reported} case${r.total_cases_reported === 1 ? "" : "s"} reported`}
            </div>
            <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 4 }}>
              {r.valid_from} → {r.valid_to}
            </div>
          </div>
        )
      })}
      <div className="inline-actions">
        <button className="small-btn primary" onClick={onSpeak} type="button">
          {LISTEN_BTN[language]}
        </button>
        <button className="small-btn" onClick={onDone} type="button">
          {BACK_BTN[language]}
        </button>
      </div>
    </div>
  )
}
