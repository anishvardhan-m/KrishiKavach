// Follow-up card — SIH26131 farmer feedback / outcome loop.
//
// Fetches cases due for follow-up from GET /api/cases/due-for-follow-up and
// guides the farmer through reporting the outcome of each recommendation.
// Voice-first: the card title and buttons are designed to be spoken aloud
// via the existing VoiceController.
//
// Flow:
//   List view → [select case] → Outcome view → [submit] → Success → home
//
// Stores actual feedback data via POST /api/cases/{id}/feedback and, when
// "expert help" is chosen, also creates an escalation via the escalation API.

import { useCallback, useEffect, useState } from "react"
import type { CaseResponse } from "../types"
import type { VoiceLanguage } from "../services/voice"
import { getCasesDueForFollowUp, submitFeedback } from "../services/api"
import { t } from "../i18n/strings"
import { escalateCase } from "../services/api" // uses existing escalation endpoint

type Outcome = "improved" | "not_improved" | "expert_help"

function formatDate(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return `${d.getFullYear()}-${(d.getMonth() + 1).toString().padStart(2, "0")}-${d.getDate().toString().padStart(2, "0")}`
}

function CaseList({
  cases,
  loading,
  error,
  onSelect,
}: {
  cases: CaseResponse[]
  loading: boolean
  error: string | null
  onSelect: (c: CaseResponse) => void
}) {
  if (loading) {
    return (
      <div className="loading">
        <div className="spinner" />
        {t("follow_up_loading", "hi-IN")}
      </div>
    )
  }
  if (error) {
    return <div className="error">{error}</div>
  }
  if (cases.length === 0) {
    return (
      <div>
        <p style={{ margin: "0 0 8px", fontWeight: 600 }}>{t("follow_up_none", "hi-IN")}</p>
        <p style={{ margin: 0, color: "#475569", fontSize: 14 }}>
          {t("follow_up_none_body", "hi-IN")}
        </p>
      </div>
    )
  }
  return (
    <div>
      <p style={{ margin: "0 0 12px", color: "#475569", fontSize: 15 }}>
        {t("follow_up_select", "hi-IN")}
      </p>
      <ul className="officer-list">
        {cases.map((c, i) => (
          <li
            key={c.id}
            onClick={() => onSelect(c)}
            style={{ cursor: "pointer" }}
          >
            <span className="tag">{i + 1}</span>
            <strong>{c.predicted_disease || "Unknown"}</strong>
            {c.predicted_crop && (
              <span style={{ color: "#475569" }}> · {c.predicted_crop}</span>
            )}
            <span className="officer-list-meta">
              {t("follow_up_case_label", "hi-IN")} · {formatDate(c.detected_at)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function OutcomeView({
  case_,
  onSubmit,
  onBack,
  submitting,
}: {
  case_: CaseResponse
  onSubmit: (outcome: Outcome, notes: string) => void
  onBack: () => void
  submitting: boolean
}) {
  const [notes, setNotes] = useState("")

  return (
    <div>
      <p style={{ margin: "0 0 16px", fontWeight: 600, color: "#14532d", fontSize: 16 }}>
        {case_.predicted_disease || "Unknown disease"}
        {case_.predicted_crop ? ` — ${case_.predicted_crop}` : ""}
      </p>

      <p style={{ margin: "0 0 16px", color: "#475569", fontSize: 15 }}>
        {t("follow_up_confirm_body", "hi-IN")}
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <button
          className="action-btn green"
          onClick={() => onSubmit("improved", notes)}
          disabled={submitting}
          type="button"
          style={{ borderRadius: 14, minHeight: 60, fontSize: 18 }}
        >
          <span className="icon">✓</span>
          <span className="label">{t("follow_up_case_improved", "hi-IN")}</span>
        </button>

        <button
          className="action-btn orange"
          onClick={() => onSubmit("not_improved", notes)}
          disabled={submitting}
          type="button"
          style={{ borderRadius: 14, minHeight: 60, fontSize: 18 }}
        >
          <span className="icon">✕</span>
          <span className="label">{t("follow_up_case_not_improved", "hi-IN")}</span>
        </button>

        <button
          className="action-btn red"
          onClick={() => onSubmit("expert_help", notes)}
          disabled={submitting}
          type="button"
          style={{ borderRadius: 14, minHeight: 60, fontSize: 18 }}
        >
          <span className="icon">🆘</span>
          <span className="label">{t("follow_up_case_expert", "hi-IN")}</span>
        </button>
      </div>

      <div style={{ marginTop: 16 }}>
        <label
          htmlFor="follow-up-notes"
          style={{ display: "block", fontSize: 13, color: "#475569", marginBottom: 4 }}
        >
          {t("follow_up_notes_placeholder", "hi-IN")}
        </label>
        <textarea
          id="follow-up-notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          maxLength={1000}
          style={{
            width: "100%",
            padding: 10,
            borderRadius: 8,
            border: "1px solid #d1d5db",
            fontSize: 14,
            fontFamily: "inherit",
            boxSizing: "border-box",
          }}
          placeholder=""
        />
      </div>

      <div style={{ marginTop: 12 }}>
        <button
          className="small-btn"
          onClick={onBack}
          disabled={submitting}
          type="button"
        >
          ← {t("follow_up_back", "hi-IN")}
        </button>
      </div>
    </div>
  )
}

function SuccessView({
  outcome,
  onDone,
}: {
  outcome: Outcome
  onDone: () => void
}) {
  const messages: Record<Outcome, string> = {
    improved: t("follow_up_success_improved", "hi-IN"),
    not_improved: t("follow_up_success_not_improved", "hi-IN"),
    expert_help: t("follow_up_success_expert", "hi-IN"),
  }
  const icons: Record<Outcome, string> = {
    improved: "✓",
    not_improved: "↻",
    expert_help: "🆘",
  }

  return (
    <div style={{ textAlign: "center", padding: "20px 0" }}>
      <div
        style={{
          width: 60,
          height: 60,
          borderRadius: "50%",
          background: "#dcfce7",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 28,
          margin: "0 auto 16px",
        }}
      >
        {icons[outcome]}
      </div>
      <p style={{ fontSize: 18, fontWeight: 600, margin: "0 0 16px" }}>
        {messages[outcome]}
      </p>
      <button className="small-btn primary" onClick={onDone} type="button">
        ✓ {t("follow_up_back", "hi-IN")}
      </button>
    </div>
  )
}

interface FollowUpCardProps {
  onDone: () => void
  onSpeak: (text: string) => Promise<void>
  language: VoiceLanguage
}

export function FollowUpCard({ onDone, onSpeak, language }: FollowUpCardProps) {
  const [cases, setCases] = useState<CaseResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<CaseResponse | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [successOutcome, setSuccessOutcome] = useState<Outcome | null>(null)

  // Fetch due cases on mount.
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getCasesDueForFollowUp()
      .then((data) => {
        if (cancelled) return
        setCases(data)
      })
      .catch((e) => {
        if (cancelled) return
        setError(e?.message || "Could not load follow-up cases.")
      })
      .finally(() => {
        if (cancelled) return
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Speak when cases load.
  useEffect(() => {
    if (loading) return
    if (cases.length === 0) {
      onSpeak(t("follow_up_none", language)).catch(() => {})
    } else {
      onSpeak(
        `${cases.length} ${language === "hi-IN" ? "रिकॉर्ड मिले। कृपया अपनी सिफ़ारिश चुनें।" : `${cases.length} records found. Please select your case.`}`,
      ).catch(() => {})
    }
  }, [loading, cases.length, language, onSpeak])

  const handleSubmit = useCallback(
    async (outcome: Outcome, notes: string) => {
      if (!selected) return
      setSubmitting(true)
      setSubmitError(null)
      try {
        await submitFeedback(selected.id, outcome, notes || undefined)
        // If expert help, also create an escalation.
        if (outcome === "expert_help") {
          try {
            await escalateCase(selected.id, notes || "Farmer requested expert help via follow-up")
          } catch {
            // Escalation failure is non-fatal — feedback was already stored.
          }
        }
        setSuccessOutcome(outcome)
        const successMessages: Record<Outcome, string> = {
          improved: t("follow_up_success_improved", language),
          not_improved: t("follow_up_success_not_improved", language),
          expert_help: t("follow_up_success_expert", language),
        }
        onSpeak(successMessages[outcome]).catch(() => {})
      } catch (e: any) {
        setSubmitError(e?.message || t("follow_up_error", language))
        onSpeak(t("follow_up_error", language)).catch(() => {})
      } finally {
        setSubmitting(false)
      }
    },
    [selected, language, onSpeak],
  )

  return (
    <div className="card" role="region" aria-label="Follow-up">
      <h2>{t("follow_up_title", language)}</h2>

      {successOutcome !== null ? (
        <SuccessView outcome={successOutcome} onDone={onDone} />
      ) : selected !== null ? (
        <OutcomeView
          case_={selected}
          onSubmit={handleSubmit}
          onBack={() => setSelected(null)}
          submitting={submitting}
        />
      ) : (
        <CaseList
          cases={cases}
          loading={loading}
          error={error}
          onSelect={setSelected}
        />
      )}

      {submitError && <div className="error" style={{ marginTop: 10 }}>{submitError}</div>}

      <div style={{ marginTop: 16 }}>
        <button className="small-btn" onClick={onDone} type="button">
          ← {t("follow_up_back", language)}
        </button>
      </div>
    </div>
  )
}
