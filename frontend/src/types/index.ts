// Shared types between frontend and backend
export interface PredictionResult {
  disease: string
  crop: string
  confidence: number
  severity: 'low' | 'medium' | 'high'
  uncertainty_flag: boolean
  description: string
  disease_slug: string
  recommendation_text: string
  steps: string[]
  warning: string | null
  escalate: boolean
  follow_up_days: number
  is_demo: boolean
  model_source: string
  alternatives: Array<{ disease: string; crop: string; confidence: number }>
}

export interface RiskForecast {
  risk_score: number
  risk_level: "low" | "medium" | "high" | "critical"
  recommended_action: string
  explanation: string
  // contributing_factors is available in the API response but intentionally
  // hidden from the farmer-facing card — it is for officer/expert UIs only.
  contributing_factors?: unknown
}

export interface CaseCreateResponse {
  case_id: string
  prediction: PredictionResult
  farmer_id: string
  farm_id: string
  detected_at: string
  recommendation_given_at: string
  next_follow_up_at: string
  case_status: string
  is_demo_prediction: boolean
  risk_forecast?: RiskForecast
}

export interface CaseResponse {
  id: string
  farm_id: string
  farmer_id: string
  image_path: string | null
  predicted_disease: string | null
  predicted_crop: string | null
  confidence: number | null
  severity: string | null
  uncertainty_flag: boolean
  detected_at: string
  recommendation_given_at: string | null
  treatment_attempted_at: string | null
  next_follow_up_at: string
  last_follow_up_at: string | null
  case_status: string
  notes: string | null
  // Escalation overlay (added by GET /api/cases/{id})
  escalation_status?: "active" | "resolved" | null
  latest_verdict?: Verdict | null
}

export interface FeedbackRequest {
  attempted_intervention: boolean
  crop_improved: boolean | null
  farmer_notes: string | null
}

export interface FeedbackResponse {
  id: string
  case_id: string
  feedback_at: string
  attempted_intervention: boolean
  crop_improved: boolean | null
  farmer_notes: string | null
}

export interface DiseaseReport {
  id: string
  district: string | null
  crop_type: string | null
  disease_type: string | null
  risk_level: string | null
  affected_farms: number
  total_cases_reported: number
  valid_from: string
  valid_to: string
}

export interface HealthResponse {
  status: string
  database: string
  prediction_mode: string
  demo_time_enabled: boolean
  current_demo_date: string | null
  version: string
}

export interface VoiceIntent {
  raw_text: string
  intent: 'yes' | 'no' | 'retry' | 'escalate' | 'silence' | 'unknown'
  confidence: number
  language: string
}

// ---------------------------------------------------------------------------
// Officer dashboard types
// ---------------------------------------------------------------------------

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

export interface DiseaseBreakdownEntry {
  crop: string
  disease: string
  case_count: number
  farm_count: number
  severity: string
  risk_level: string
  last_detected: string | null
}

export interface InterventionStats {
  total_feedbacks: number
  attempted_treatment: number
  crop_improved: number
  crop_not_improved: number
  no_feedback_yet: number
}

export interface OutbreakSummary {
  crop_type: string
  disease_type: string
  risk_level: string
  affected_farms: number
  total_cases_reported: number
}

export interface WeatherSummary {
  soil_moisture_percent: number | null
  evapotranspiration_mm: number | null
  temperature_c: number | null
  humidity_percent: number | null
  recorded_at: string | null
}

export interface DistrictRiskProfile {
  risk_score: number
  risk_level: RiskLevel
  recommended_action: string
  explanation: string
  contributing_factors?: RiskFactorBreakdown[] | null
}

export interface RiskFactorBreakdown {
  name: string
  weight: number
  raw_signal: number
  contribution: number
  note: string
}

export interface DistrictSummary {
  district: string
  state: string
  centroid_lon: number | null
  centroid_lat: number | null
  total_cases: number
  active_cases: number
  resolved_cases: number
  escalated_cases: number
  follow_up_due: number
  severity_low: number
  severity_medium: number
  severity_high: number
  disease_breakdown: DiseaseBreakdownEntry[]
  interventions: InterventionStats | null
  active_outbreaks: OutbreakSummary[]
  weather: WeatherSummary | null
  risk_profile: DistrictRiskProfile | null
  computed_at: string
}

// ---------------------------------------------------------------------------
// Expert escalation types
// ---------------------------------------------------------------------------

export type Verdict = "confirmed" | "rejected" | "needs_more_evidence"

export interface EscalationResponse {
  id: string
  case_id: string
  expert_id: string | null
  expert_name: string | null
  escalated_at: string
  resolved_at: string | null
  expert_notes: string | null
  expert_verdict: Verdict | null
  // Lightweight case context (no farmer PII)
  predicted_disease: string | null
  predicted_crop: string | null
  severity: string | null
  district: string | null
  uncertainty_flag: boolean
}
