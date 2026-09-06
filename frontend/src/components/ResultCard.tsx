// Result card — shows the prediction outcome to the farmer in plain language.
// Hides technical details; clearly marks the result as a demo / rule-based prediction.

import type { PredictionResult } from "../types"
import type { VoiceLanguage } from "../services/voice"
import { t } from "../i18n/strings"

interface Props {
  prediction: PredictionResult
  language: VoiceLanguage
  onSpeakAgain: () => void
  onDone: () => void
}

const SEVERITY_CLASS: Record<string, string> = {
  low: "severity-low",
  medium: "severity-medium",
  high: "severity-high",
}

const SEVERITY_TEXT: Record<VoiceLanguage, Record<string, string>> = {
  "hi-IN": { low: "हल्का", medium: "मध्यम", high: "गंभीर" },
  "mr-IN": { low: "हलका", medium: "मध्यम", high: "गंभीर" },
  "en-IN": { low: "Mild", medium: "Moderate", high: "Severe" },
}

export function ResultCard({ prediction, language, onSpeakAgain, onDone }: Props) {
  const isDemo = prediction.is_demo
  const confidencePct = Math.round(prediction.confidence * 100)
  const severityClass = SEVERITY_CLASS[prediction.severity] || "severity-medium"
  const severityLabel = SEVERITY_TEXT[language]?.[prediction.severity] || prediction.severity

  return (
    <div className="card" role="region" aria-label="Diagnosis result">
      <h2>
        {prediction.disease}
        {prediction.crop && prediction.crop !== "Unknown" && (
          <span style={{ color: "#475569", fontWeight: 500, fontSize: 18 }}>
            {" "}— {prediction.crop}
          </span>
        )}
      </h2>

      <div className="meta">
        <span className={`tag ${severityClass}`}>{severityLabel}</span>
        {prediction.uncertainty_flag && (
          <span className="tag uncertain">{t("not_fully_sure", language)}</span>
        )}
        {isDemo && <span className="tag demo">DEMO</span>}
      </div>

      <p>{prediction.description}</p>

      {prediction.uncertainty_flag && (
        <div className="warning-box">{t("result_uncertain_warning", language)}</div>
      )}

      <h3 style={{ margin: "16px 0 8px", fontSize: 18, color: "#14532d" }}>
        {language === "hi-IN" ? "क्या करना है" : language === "mr-IN" ? "काय करावे" : "What to do"}
      </h3>
      <p>{prediction.recommendation_text}</p>

      {prediction.steps && prediction.steps.length > 0 && (
        <ol className="steps">
          {prediction.steps.map((step, i) => (
            <li key={i}>{step}</li>
          ))}
        </ol>
      )}

      {prediction.warning && (
        <div className="warning-box">⚠️ {prediction.warning}</div>
      )}

      <div className="inline-actions">
        <button className="small-btn primary" onClick={onSpeakAgain} type="button">
          🔊 {language === "hi-IN" ? "फिर से सुनें" : language === "mr-IN" ? "पुन्हा ऐका" : "Listen again"}
        </button>
        <button className="small-btn" onClick={onDone} type="button">
          ✓ {language === "hi-IN" ? "ठीक है" : language === "mr-IN" ? "ठीक आहे" : "Done"}
        </button>
      </div>

      <p style={{ marginTop: 16, fontSize: 12, color: "#6b7280" }}>
        {t("confidence_label", language)}: {confidencePct}% — SIH demo · {prediction.model_source}
      </p>
    </div>
  )
}
