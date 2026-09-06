// Risk card — shows nearby disease outbreak information for the farmer's area.

import type { DiseaseReport } from "../types"

interface Props {
  reports: DiseaseReport[]
  loading: boolean
  error: string | null
  onDone: () => void
  onSpeak: () => void
}

const RISK_CLASS: Record<string, string> = {
  low: "severity-low",
  medium: "severity-medium",
  high: "severity-high",
  critical: "severity-high",
}

const RISK_LABEL: Record<string, string> = {
  low: "Low risk",
  medium: "Moderate risk",
  high: "High risk",
  critical: "Critical",
}

export function RiskCard({ reports, loading, error, onDone, onSpeak }: Props) {
  if (loading) {
    return (
      <div className="card">
        <div className="loading">
          <div className="spinner" />
          Looking for nearby risk information...
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="card">
        <h2>Nearby risk</h2>
        <div className="error">{error}</div>
        <div className="inline-actions">
          <button className="small-btn" onClick={onDone} type="button">
            ← Back
          </button>
        </div>
      </div>
    )
  }

  if (reports.length === 0) {
    return (
      <div className="card">
        <h2>Nearby risk</h2>
        <p>
          No active disease outbreaks have been reported in your area right
          now. Keep checking your crop regularly.
        </p>
        <div className="inline-actions">
          <button className="small-btn primary" onClick={onSpeak} type="button">
            🔊 Listen
          </button>
          <button className="small-btn" onClick={onDone} type="button">
            ← Back
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="card" role="region" aria-label="Nearby risk">
      <h2>Nearby risk</h2>
      <p style={{ color: "#475569", fontSize: 15 }}>
        {reports.length} active outbreak report{reports.length === 1 ? "" : "s"} in your region:
      </p>
      {reports.map((r) => {
        const cls = RISK_CLASS[r.risk_level || "medium"] || "severity-medium"
        const lbl = RISK_LABEL[r.risk_level || "medium"] || r.risk_level
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
              {r.district && (
                <span className="tag">{r.district}</span>
              )}
              {r.crop_type && (
                <span className="tag">{r.crop_type}</span>
              )}
            </div>
            <div style={{ fontWeight: 600, fontSize: 16 }}>
              {r.disease_type || "Unknown disease"}
            </div>
            <div style={{ fontSize: 13, color: "#6b7280", marginTop: 4 }}>
              {r.affected_farms} farm{r.affected_farms === 1 ? "" : "s"} affected ·
              {" "}
              {r.total_cases_reported} case{r.total_cases_reported === 1 ? "" : "s"} reported
            </div>
            <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 4 }}>
              {r.valid_from} → {r.valid_to}
            </div>
          </div>
        )
      })}
      <div className="inline-actions">
        <button className="small-btn primary" onClick={onSpeak} type="button">
          🔊 Listen
        </button>
        <button className="small-btn" onClick={onDone} type="button">
          ← Back
        </button>
      </div>
    </div>
  )
}
