// Expert Review Queue — SIH26131 expert verification workflow.
//
// Uses the existing GET /api/escalations and POST /api/escalations/{id}/verdict
// endpoints.  Shows a compact review queue of active escalations, lets the
// expert open a case detail, view the AI diagnosis, and submit one of three
// verdicts.  After a verdict, the item is removed from the active queue
// and the user is returned to the list.
//
// Privacy: this component NEVER shows farmer names, phone numbers, or
// farmer IDs.  The API does not expose them, and the component renders
// only district, crop, AI diagnosis, severity, confidence, and timestamps.

import { useCallback, useEffect, useState } from "react"
import type { CaseResponse, EscalationResponse, Verdict } from "../types"
import { getCase, getEscalation, listEscalations, submitVerdict } from "../services/api"

type QueueItem = EscalationResponse

interface ExpertReviewQueueProps {
  onExit: () => void
}

const SEVERITY_COLOR: Record<string, string> = {
  low: "#16a34a",
  medium: "#eab308",
  high: "#f97316",
  critical: "#dc2626",
}

function formatTime(iso: string | null): string {
  if (!iso) return "—"
  // Trim to YYYY-MM-DD HH:MM for compact display
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const pad = (n: number) => n.toString().padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function RiskBadge({ severity }: { severity: string | null }) {
  const s = (severity || "low").toLowerCase()
  const color = SEVERITY_COLOR[s] || SEVERITY_COLOR.low
  return (
    <span
      className="tag"
      style={{ background: color, color: "#ffffff", textTransform: "capitalize" }}
    >
      {s}
    </span>
  )
}

function QueueList({
  items,
  selectedId,
  onSelect,
  loading,
  error,
}: {
  items: QueueItem[]
  selectedId: string | null
  onSelect: (id: string) => void
  loading: boolean
  error: string | null
}) {
  if (loading) {
    return (
      <div className="card">
        <div className="loading">
          <div className="spinner" />
          Loading expert review queue…
        </div>
      </div>
    )
  }
  if (error) {
    return <div className="error">{error}</div>
  }
  if (items.length === 0) {
    return (
      <div className="card">
        <p style={{ margin: 0 }}>No active escalations. The queue is clear.</p>
      </div>
    )
  }
  return (
    <ul className="officer-list" aria-label="Escalation queue">
      {items.map((it) => {
        const isSelected = it.id === selectedId
        return (
          <li
            key={it.id}
            onClick={() => onSelect(it.id)}
            style={{
              cursor: "pointer",
              outline: isSelected ? "2px solid #0f172a" : "none",
              background: isSelected ? "#f1f5f9" : "#f8fafc",
            }}
          >
            <RiskBadge severity={it.severity} />
            <strong>{it.predicted_disease || "Unknown disease"}</strong>
            {it.predicted_crop && (
              <span style={{ color: "#475569" }}>· {it.predicted_crop}</span>
            )}
            <span className="officer-list-meta">
              {it.district ? `· ${it.district} ` : ""}
              · escalated {formatTime(it.escalated_at)}
            </span>
            {it.uncertainty_flag && (
              <span className="tag uncertain" style={{ marginLeft: 4 }}>
                uncertain
              </span>
            )}
          </li>
        )
      })}
    </ul>
  )
}

function ReviewDetail({
  escalation,
  onVerdictSubmitted,
  onClose,
}: {
  escalation: QueueItem
  onVerdictSubmitted: (verdict: Verdict) => void
  onClose: () => void
}) {
  const [caseData, setCaseData] = useState<CaseResponse | null>(null)
  const [loadingCase, setLoadingCase] = useState(true)
  const [caseError, setCaseError] = useState<string | null>(null)
  const [notes, setNotes] = useState("")
  const [submitting, setSubmitting] = useState<Verdict | null>(null)
  const [verdictError, setVerdictError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoadingCase(true)
    setCaseError(null)
    getCase(escalation.case_id)
      .then((data) => {
        if (cancelled) return
        setCaseData(data)
      })
      .catch((e) => {
        if (cancelled) return
        setCaseError(e?.message || "Failed to load case")
      })
      .finally(() => {
        if (cancelled) return
        setLoadingCase(false)
      })
    return () => {
      cancelled = true
    }
  }, [escalation.case_id])

  const handleVerdict = useCallback(
    async (verdict: Verdict) => {
      setSubmitting(verdict)
      setVerdictError(null)
      try {
        await submitVerdict(escalation.id, verdict, notes || undefined)
        onVerdictSubmitted(verdict)
      } catch (e: any) {
        setVerdictError(e?.message || `Failed to submit verdict: ${verdict}`)
      } finally {
        setSubmitting(null)
      }
    },
    [escalation.id, notes, onVerdictSubmitted],
  )

  // Optional: derive an image URL from the case's image_path. The backend
  // stores a relative path like "/uploads/abc.jpg"; we let the browser
  // request it directly via Vite proxy in dev, and via the API origin
  // in production.
  const imagePath = caseData?.image_path ?? null
  const imageUrl = imagePath
    ? imagePath.startsWith("http")
      ? imagePath
      : imagePath.startsWith("/")
      ? imagePath
      : `/${imagePath}`
    : null

  const confidence =
    caseData?.confidence !== null && caseData?.confidence !== undefined
      ? Math.round(caseData.confidence * 100)
      : null

  return (
    <div className="officer-detail" aria-label="Escalation review detail">
      <div className="officer-detail-header">
        <h2>
          {escalation.predicted_disease || "Unknown disease"}
          {escalation.predicted_crop && (
            <span className="officer-state">· {escalation.predicted_crop}</span>
          )}
        </h2>
        <button className="small-btn" onClick={onClose} type="button">
          ← Back to queue
        </button>
      </div>

      <div className="officer-detail-risk">
        <RiskBadge severity={escalation.severity} />
        {confidence !== null && (
          <span className="officer-risk-score">AI confidence: {confidence}%</span>
        )}
        {escalation.uncertainty_flag && (
          <span className="tag uncertain">uncertain prediction</span>
        )}
      </div>

      {escalation.expert_notes && (
        <p className="officer-detail-explanation">
          <strong>Escalation reason: </strong>
          {escalation.expert_notes}
        </p>
      )}

      {imageUrl && (
        <div className="preview-wrap">
          <img className="preview-img" src={imageUrl} alt="Case photo" />
        </div>
      )}

      <h3 className="officer-section-title">AI diagnosis</h3>
      {loadingCase ? (
        <p className="officer-detail-empty-text">Loading case data…</p>
      ) : caseError ? (
        <p className="officer-detail-empty-text">{caseError}</p>
      ) : (
        <div className="officer-detail-grid">
          <div>
            <div className="officer-tile-label">Disease</div>
            <div className="officer-tile-value-sm">
              {caseData?.predicted_disease || "—"}
            </div>
          </div>
          <div>
            <div className="officer-tile-label">Crop</div>
            <div className="officer-tile-value-sm">
              {caseData?.predicted_crop || "—"}
            </div>
          </div>
          <div>
            <div className="officer-tile-label">Severity</div>
            <div className="officer-tile-value-sm">
              {caseData?.severity || "—"}
            </div>
          </div>
          <div>
            <div className="officer-tile-label">Confidence</div>
            <div className="officer-tile-value-sm">
              {confidence !== null ? `${confidence}%` : "—"}
            </div>
          </div>
          <div>
            <div className="officer-tile-label">Detected</div>
            <div className="officer-tile-value-sm">
              {formatTime(caseData?.detected_at || null)}
            </div>
          </div>
          <div>
            <div className="officer-tile-label">Case status</div>
            <div className="officer-tile-value-sm">
              {caseData?.case_status || "—"}
            </div>
          </div>
        </div>
      )}

      <h3 className="officer-section-title">Submit expert verdict</h3>
      <p style={{ margin: 0, fontSize: 14, color: "#475569" }}>
        Choose one. The case status will be updated automatically:
        "confirmed" returns the case to active follow-up, "rejected"
        closes it, and "needs_more_evidence" reopens it for additional
        farmer input.
      </p>
      <div className="inline-actions" style={{ marginTop: 10 }}>
        <button
          className="small-btn primary"
          onClick={() => handleVerdict("confirmed")}
          disabled={submitting !== null}
          type="button"
          style={{ background: "#16a34a", borderColor: "#16a34a", color: "#fff" }}
        >
          {submitting === "confirmed" ? "Submitting…" : "✓ Confirm"}
        </button>
        <button
          className="small-btn"
          onClick={() => handleVerdict("rejected")}
          disabled={submitting !== null}
          type="button"
          style={{ background: "#dc2626", borderColor: "#dc2626", color: "#fff" }}
        >
          {submitting === "rejected" ? "Submitting…" : "✕ Reject"}
        </button>
        <button
          className="small-btn"
          onClick={() => handleVerdict("needs_more_evidence")}
          disabled={submitting !== null}
          type="button"
          style={{ background: "#f97316", borderColor: "#f97316", color: "#fff" }}
        >
          {submitting === "needs_more_evidence"
            ? "Submitting…"
            : "↻ Needs More Evidence"}
        </button>
      </div>

      <div style={{ marginTop: 12 }}>
        <label
          htmlFor="expert-notes"
          style={{ display: "block", fontSize: 13, color: "#475569", marginBottom: 4 }}
        >
          Optional notes
        </label>
        <textarea
          id="expert-notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          maxLength={2000}
          style={{
            width: "100%",
            padding: 10,
            borderRadius: 8,
            border: "1px solid #d1d5db",
            fontSize: 14,
            fontFamily: "inherit",
            boxSizing: "border-box",
          }}
          placeholder="e.g. symptoms match bacterial wilt; recommend soil drench."
        />
      </div>

      {verdictError && <div className="error" style={{ marginTop: 10 }}>{verdictError}</div>}
    </div>
  )
}

export function ExpertReviewQueue({ onExit }: ExpertReviewQueueProps) {
  const [items, setItems] = useState<QueueItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listEscalations("active")
      setItems(data.escalations)
      // If the previously selected item is no longer in the queue, clear it.
      setSelectedId((prev) => (prev && data.escalations.some((e) => e.id === prev) ? prev : null))
    } catch (e: any) {
      setError(e?.message || "Failed to load escalations")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const handleVerdictSubmitted = useCallback(() => {
    // Refresh the active queue — the resolved item is gone.
    refresh()
  }, [refresh])

  const selected = items.find((i) => i.id === selectedId) || null

  return (
    <div className="officer-dashboard">
      <div className="officer-header">
        <div>
          <div className="officer-eyebrow">SIH26131 · Expert Review</div>
          <h1>Expert Review Queue</h1>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            className="small-btn"
            onClick={refresh}
            type="button"
            title="Refresh queue"
          >
            ↻ Refresh
          </button>
          <button className="small-btn" onClick={onExit} type="button">
            ← Officer view
          </button>
        </div>
      </div>

      <div className="officer-disclaimer">
        Cases awaiting expert verification. Each item shows the AI diagnosis,
        severity, confidence, and the escalation reason. No farmer PII is
        shown.
      </div>

      {selected ? (
        <ReviewDetail
          escalation={selected}
          onVerdictSubmitted={handleVerdictSubmitted}
          onClose={() => setSelectedId(null)}
        />
      ) : (
        <div className="officer-main" style={{ gridTemplateColumns: "minmax(0, 1fr)" }}>
          <div className="officer-detail">
            <h3 className="officer-section-title" style={{ marginTop: 0, borderTop: 0, paddingTop: 0 }}>
              Active escalations ({items.length})
            </h3>
            <QueueList
              items={items}
              selectedId={selectedId}
              onSelect={setSelectedId}
              loading={loading}
              error={error}
            />
          </div>
        </div>
      )}
    </div>
  )
}
