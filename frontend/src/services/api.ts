// Backend API client.
// All calls go to the existing FastAPI backend via Vite proxy (/api/* → localhost:8000).

import type {
  CaseCreateResponse,
  CaseResponse,
  DiseaseReport,
  DistrictSummary,
  EscalationResponse,
} from "../types"

const API_BASE = "" // rely on Vite dev proxy

export async function predictImage(
  file: File,
  district?: string,
  cropType?: string,
  cropStage?: string,
  farmerLanguage = "marathi",
): Promise<CaseCreateResponse> {
  const form = new FormData()
  form.append("file", file)
  if (district) form.append("district", district)
  if (cropType) form.append("crop_type", cropType)
  if (cropStage) form.append("crop_stage", cropStage)
  form.append("farmer_language", farmerLanguage)

  const res = await fetch(`${API_BASE}/api/predict`, {
    method: "POST",
    body: form,
  })
  if (!res.ok) {
    let detail = `Prediction failed (${res.status})`
    try {
      const data = await res.json()
      if (data?.detail) detail = data.detail
    } catch {
      /* noop */
    }
    throw new Error(detail)
  }
  return res.json()
}

export async function listCases(farmerId?: string): Promise<CaseResponse[]> {
  const qs = farmerId ? `?farmer_id=${farmerId}` : ""
  const res = await fetch(`${API_BASE}/api/cases${qs}`)
  if (!res.ok) throw new Error(`Failed to load cases (${res.status})`)
  const data = await res.json()
  return data.cases as CaseResponse[]
}

export async function listOutbreaks(district?: string): Promise<DiseaseReport[]> {
  const qs = district ? `?district=${encodeURIComponent(district)}` : ""
  const res = await fetch(`${API_BASE}/api/outbreaks${qs}`)
  if (!res.ok) throw new Error(`Failed to load outbreaks (${res.status})`)
  return res.json()
}

export async function getCase(caseId: string): Promise<CaseResponse> {
  const res = await fetch(`${API_BASE}/api/cases/${caseId}`)
  if (!res.ok) throw new Error(`Case not found (${res.status})`)
  return res.json()
}

/**
 * Escalate a case to the expert review queue.
 */
export async function escalateCase(caseId: string, reason?: string): Promise<EscalationResponse> {
  const body: Record<string, string> = {}
  if (reason) body.reason = reason
  const res = await fetch(`${API_BASE}/api/cases/${encodeURIComponent(caseId)}/escalate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = `Escalation failed (${res.status})`
    try {
      const data = await res.json()
      if (data?.detail) detail = data.detail
    } catch { /* noop */ }
    throw new Error(detail)
  }
  return res.json()
}

/**
 * Expert escalation queue — fetches active escalations for expert review.
 *
 * - `status`: "active" (default), "resolved", or "all".
 *   Farmer PII is never included in the response.
 */
export async function listEscalations(
  status: "active" | "resolved" | "all" = "active",
): Promise<{ escalations: EscalationResponse[]; total: number }> {
  const res = await fetch(`${API_BASE}/api/escalations?status=${encodeURIComponent(status)}`)
  if (!res.ok) {
    throw new Error(`Failed to load escalations (${res.status})`)
  }
  return res.json()
}

/**
 * Fetch a single escalation by ID.
 */
export async function getEscalation(
  escalationId: string,
): Promise<EscalationResponse> {
  const res = await fetch(`${API_BASE}/api/escalations/${encodeURIComponent(escalationId)}`)
  if (!res.ok) throw new Error(`Escalation not found (${res.status})`)
  return res.json()
}

/**
 * Submit an expert verdict on an escalation.
 *
 * `verdict`: "confirmed" | "rejected" | "needs_more_evidence"
 */
export async function submitVerdict(
  escalationId: string,
  verdict: "confirmed" | "rejected" | "needs_more_evidence",
  expertNotes?: string,
): Promise<EscalationResponse> {
  const body: Record<string, string> = {
    verdict,
    // computed_at is required by the schema; the backend stores it in the
    // verdict record. ISO 8601 format.
    computed_at: new Date().toISOString().split("T")[0],
  }
  if (expertNotes) body.expert_notes = expertNotes
  const res = await fetch(`${API_BASE}/api/escalations/${encodeURIComponent(escalationId)}/verdict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = `Verdict failed (${res.status})`
    try {
      const data = await res.json()
      if (data?.detail) detail = data.detail
    } catch { /* noop */ }
    throw new Error(detail)
  }
  return res.json()
}

/**
 * Officer dashboard — district-level summary.
 *
 * - `district`: optional filter; if omitted, returns summaries for all
 *   Maharashtra districts.
 * - `includeFactors`: optional; when true, includes the per-factor risk
 *   breakdown (weights, contributions) in each district's risk_profile.
 *   Defaults to false to keep payloads small for the heatmap view.
 */
/**
 * Follow-up — fetch cases due for follow-up.
 *
 * Without farmerId (demo mode), returns all due cases so the farmer
 * can identify their own by disease/crop name.
 */
export async function getCasesDueForFollowUp(
  farmerId?: string,
): Promise<CaseResponse[]> {
  const qs = farmerId ? `?farmer_id=${encodeURIComponent(farmerId)}` : ""
  const res = await fetch(`${API_BASE}/api/cases/due-for-follow-up${qs}`)
  if (!res.ok) throw new Error(`Failed to load follow-up cases (${res.status})`)
  const data = await res.json()
  return (data.cases ?? []) as CaseResponse[]
}

/**
 * Submit farmer feedback for a case outcome.
 *
 * Stores actual data in the existing CaseFeedback table and updates
 * the case status: improved → resolved, not improved → active (new
 * follow-up scheduled), expert help → active (escalation created).
 *
 * `outcome`: "improved" | "not_improved" | "expert_help"
 */
export async function submitFeedback(
  caseId: string,
  outcome: "improved" | "not_improved" | "expert_help",
  notes?: string,
): Promise<void> {
  const body: Record<string, unknown> = {
    attempted_intervention: outcome !== "improved", // assume they tried if not fully better
    crop_improved: outcome === "improved" ? true : false,
    farmer_notes: notes || undefined,
  }
  const res = await fetch(`${API_BASE}/api/cases/${encodeURIComponent(caseId)}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = `Feedback failed (${res.status})`
    try {
      const data = await res.json()
      if (data?.detail) detail = data.detail
    } catch { /* noop */ }
    throw new Error(detail)
  }
}

export async function getOfficerDistrictSummary(
  district?: string,
  includeFactors = false,
): Promise<DistrictSummary[]> {
  const qs = new URLSearchParams()
  if (district) qs.set("district", district)
  if (includeFactors) qs.set("include_factors", "true")
  const suffix = qs.toString() ? `?${qs.toString()}` : ""
  const res = await fetch(`${API_BASE}/api/officer/district-summary${suffix}`)
  if (!res.ok) {
    throw new Error(`Failed to load district summary (${res.status})`)
  }
  return res.json()
}
