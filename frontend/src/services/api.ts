// Backend API client.
// All calls go to the existing FastAPI backend via Vite proxy (/api/* → localhost:8000).

import type { CaseCreateResponse, CaseResponse, DiseaseReport } from "../types"

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
