// Result card — shows the prediction outcome to the farmer in plain language.
// Hides technical details; clearly marks the result as a demo / rule-based prediction.

import type { PredictionResult } from "../types"

interface Props {
  prediction: PredictionResult
  onSpeakAgain: () => void
  onDone: () => void
}

const SEVERITY_COPY: Record<string, string> = {
  low: "Mild",
  medium: "Moderate",
  high: "Severe",
}

const SEVERITY_CLASS: Record<string, string> = {
  low: "severity-low",
  medium: "severity-medium",
  high: "severity-high",
}

export function ResultCard({ prediction, onSpeakAgain, onDone }: Props) {
  const isDemo = prediction.is_demo
  const confidencePct = Math.round(prediction.confidence * 100)
  const severityClass = SEVERITY_CLASS[prediction.severity] || "severity-medium"
  const severityLabel = SEVERITY_COPY[prediction.severity] || prediction.severity

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
        <span className={`tag ${severityClass}`}>
          {severityLabel}
        </span>
        {prediction.uncertainty_flag && (
          <span className="tag uncertain">Not fully sure</span>
        )}
        {isDemo && <span className="tag demo">DEMO</span>}
      </div>

      <p>{prediction.description}</p>

      {prediction.uncertainty_flag && (
        <div className="warning-box">
          We are not fully sure about this. Please call an expert if the
          problem gets worse.
        </div>
      )}

      <h3 style={{ margin: "16px 0 8px", fontSize: 18, color: "#14532d" }}>
        What to do
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
          🔊 Listen again
        </button>
        <button className="small-btn" onClick={onDone} type="button">
          ✓ Done
        </button>
      </div>

      <p
        style={{
          marginTop: 16,
          fontSize: 12,
          color: "#6b7280",
        }}
      >
        Confidence: {confidencePct}% — for SIH demo using {prediction.model_source}
      </p>
    </div>
  )
}
