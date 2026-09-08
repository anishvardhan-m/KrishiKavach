// Early Warning card — farmer-facing view of the risk forecast.
//
// Shows ONLY:
//   - risk level (low/medium/high/critical)
//   - one short reason
//   - immediate recommended action
//   - whether expert help is recommended
//
// The technical factor breakdown (weights, raw_signal, contribution) is
// intentionally NOT rendered here. It is available on the API response for
// future officer/expert UIs.

import type { RiskForecast } from "../types"
import type { VoiceLanguage } from "../services/voice"
import { t } from "../i18n/strings"

interface Props {
  forecast: RiskForecast
  language: VoiceLanguage
}

const RISK_CLASS: Record<string, string> = {
  low: "severity-low",
  medium: "severity-medium",
  high: "severity-high",
  critical: "severity-high",
}

function riskLabel(level: RiskForecast["risk_level"], lang: VoiceLanguage): string {
  switch (level) {
    case "low":
      return t("risk_low", lang)
    case "medium":
      return t("risk_medium", lang)
    case "high":
      return t("risk_high", lang)
    case "critical":
      return t("risk_critical", lang)
  }
}

export function EarlyWarningCard({ forecast, language }: Props) {
  const cls = RISK_CLASS[forecast.risk_level] || "severity-medium"
  const levelLabel = riskLabel(forecast.risk_level, language)
  const recommendExpert =
    forecast.risk_level === "high" || forecast.risk_level === "critical"

  return (
    <div
      className="card early-warning-card"
      role="region"
      aria-label="Early warning"
      style={{ borderLeft: "6px solid #f59e0b" }}
    >
      <h3 style={{ margin: "0 0 8px", fontSize: 18, color: "#7c2d12" }}>
        {t("risk_your_area", language)}
      </h3>

      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <span className={`tag ${cls}`} style={{ fontSize: 16, padding: "6px 12px" }}>
          {levelLabel}
        </span>
      </div>

      <p style={{ margin: "0 0 8px", color: "#374151", fontSize: 15 }}>
        <strong>{t("risk_act_now", language)}</strong>{" "}
        {forecast.recommended_action}
      </p>

      {recommendExpert && (
        <div
          className="warning-box"
          style={{ background: "#fee2e2", borderColor: "#dc2626", color: "#7f1d1d" }}
        >
          {t("risk_expert_help", language)} — {t("risk_expert_help_sub", language)}
        </div>
      )}
    </div>
  )
}