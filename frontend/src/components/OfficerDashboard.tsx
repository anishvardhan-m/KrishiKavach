// Officer Dashboard — SIH26131 Agriculture Officer command center.
//
// Visualizes the existing GET /api/officer/district-summary endpoint.
// Renders:
//   - Maharashtra-wide summary tiles
//   - SVG district-level map (centroid markers, colored by risk level)
//   - Detail panel for the selected district
//   - Optional drill-down into the per-factor risk breakdown
//
// Privacy: only aggregated, district-level data. No farmer names,
// phone numbers, or farmer IDs are ever displayed — the API does not
// expose them and this component never adds them.
//
// Map: simple equirectangular SVG projection of district centroid
// coordinates (no map library required — see README of endpoints).

import { useEffect, useMemo, useState } from "react"
import type { DistrictSummary, RiskLevel } from "../types"
import { getOfficerDistrictSummary } from "../services/api"

const RISK_COLOR: Record<RiskLevel, string> = {
  low: "#16a34a",      // green
  medium: "#eab308",   // yellow
  high: "#f97316",     // orange
  critical: "#dc2626", // red
}

const RISK_LABEL: Record<RiskLevel, string> = {
  low: "Low",
  medium: "Moderate",
  high: "High",
  critical: "Critical",
}

// Maharashtra bounding box for the SVG projection.
// Computed once; the centroid data is fixed by the backend.
const MH_LON_MIN = 72.5
const MH_LON_MAX = 80.5
const MH_LAT_MIN = 15.5
const MH_LAT_MAX = 22.0

// SVG canvas dimensions in viewBox units.
const SVG_W = 480
const SVG_H = 380

function projectToSvg(lon: number, lat: number): { x: number; y: number } {
  // Equirectangular projection with a small padding so dots don't touch
  // the edge of the canvas.
  const padX = 12
  const padY = 12
  const innerW = SVG_W - padX * 2
  const innerH = SVG_H - padY * 2
  const x = padX + ((lon - MH_LON_MIN) / (MH_LON_MAX - MH_LON_MIN)) * innerW
  // Latitude grows northwards; in SVG y grows downwards, so we invert.
  const y = padY + (1 - (lat - MH_LAT_MIN) / (MH_LAT_MAX - MH_LAT_MIN)) * innerH
  return { x, y }
}

interface SummaryTilesProps {
  summaries: DistrictSummary[]
}

function SummaryTiles({ summaries }: SummaryTilesProps) {
  const totals = useMemo(() => {
    let cases = 0
    let active = 0
    let outbreaks = 0
    let highOrCritical = 0
    for (const d of summaries) {
      cases += d.total_cases
      active += d.active_cases
      outbreaks += d.active_outbreaks.length
      if (
        d.risk_profile &&
        (d.risk_profile.risk_level === "high" ||
          d.risk_profile.risk_level === "critical")
      ) {
        highOrCritical += 1
      }
    }
    return { cases, active, outbreaks, highOrCritical }
  }, [summaries])

  return (
    <div className="officer-tiles">
      <div className="officer-tile">
        <div className="officer-tile-label">Total cases</div>
        <div className="officer-tile-value">{totals.cases}</div>
      </div>
      <div className="officer-tile">
        <div className="officer-tile-label">Active</div>
        <div className="officer-tile-value">{totals.active}</div>
      </div>
      <div className="officer-tile officer-tile-warn">
        <div className="officer-tile-label">High / Critical districts</div>
        <div className="officer-tile-value">{totals.highOrCritical}</div>
      </div>
      <div className="officer-tile">
        <div className="officer-tile-label">Active outbreaks</div>
        <div className="officer-tile-value">{totals.outbreaks}</div>
      </div>
    </div>
  )
}

interface DistrictMapProps {
  summaries: DistrictSummary[]
  selected: string | null
  onSelect: (district: string) => void
}

function DistrictMap({ summaries, selected, onSelect }: DistrictMapProps) {
  // Maharashtra outline (rough rectangle in the same projection) for context.
  // The outline is intentionally a soft rectangle; exact district polygons
  // are not bundled with the backend centroid data.
  return (
    <div className="officer-map-wrap">
      <svg
        viewBox={`0 0 ${SVG_W} ${SVG_H}`}
        className="officer-map"
        role="img"
        aria-label="Maharashtra district risk map"
      >
        <rect
          x={6}
          y={6}
          width={SVG_W - 12}
          height={SVG_H - 12}
          rx={20}
          ry={20}
          fill="#f0fdf4"
          stroke="#86efac"
          strokeWidth={2}
        />
        {/* Compass */}
        <text x={SVG_W - 36} y={24} fontSize={12} fill="#475569">
          N ↑
        </text>
        {summaries.map((d) => {
          if (d.centroid_lon === null || d.centroid_lat === null) return null
          const { x, y } = projectToSvg(d.centroid_lon, d.centroid_lat)
          const level = (d.risk_profile?.risk_level || "low") as RiskLevel
          const color = RISK_COLOR[level]
          const isSelected = d.district === selected
          const r = isSelected ? 10 : 6
          const stroke = isSelected ? "#0f172a" : "#ffffff"
          const strokeWidth = isSelected ? 2.5 : 1.5
          return (
            <g
              key={d.district}
              onClick={() => onSelect(d.district)}
              style={{ cursor: "pointer" }}
            >
              <circle cx={x} cy={y} r={r} fill={color} stroke={stroke} strokeWidth={strokeWidth}>
                <title>
                  {d.district}: {level} ({d.risk_profile?.risk_score ?? 0})
                </title>
              </circle>
            </g>
          )
        })}
      </svg>
      <div className="officer-legend" aria-label="Risk legend">
        {(["low", "medium", "high", "critical"] as RiskLevel[]).map((lvl) => (
          <div key={lvl} className="officer-legend-item">
            <span className="officer-legend-dot" style={{ background: RISK_COLOR[lvl] }} />
            <span>{RISK_LABEL[lvl]}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

interface DistrictDetailProps {
  summary: DistrictSummary | null
  loadingDetail: boolean
  includeFactors: boolean
  onToggleFactors: (next: boolean) => void
  onClose: () => void
}

function DistrictDetail({
  summary,
  loadingDetail,
  includeFactors,
  onToggleFactors,
  onClose,
}: DistrictDetailProps) {
  if (!summary) {
    return (
      <div className="officer-detail officer-detail-empty">
        <p>Select a district on the map to see details.</p>
      </div>
    )
  }

  const profile = summary.risk_profile
  const level = (profile?.risk_level || "low") as RiskLevel
  const levelColor = RISK_COLOR[level]
  const intv = summary.interventions

  return (
    <div className="officer-detail" aria-label={`${summary.district} district detail`}>
      <div className="officer-detail-header">
        <h2>
          {summary.district}
          <span className="officer-state">· {summary.state}</span>
        </h2>
        <button className="small-btn" onClick={onClose} type="button">
          ✕ Close
        </button>
      </div>

      <div className="officer-detail-risk">
        <span className="tag" style={{ background: levelColor, color: "#ffffff", fontSize: 16, padding: "6px 12px" }}>
          {RISK_LABEL[level]}
        </span>
        <span className="officer-risk-score">
          {profile?.risk_score ?? 0}/100
        </span>
      </div>

      {profile?.explanation && (
        <p className="officer-detail-explanation">{profile.explanation}</p>
      )}

      <h3 className="officer-section-title">Cases</h3>
      <div className="officer-detail-grid">
        <div>
          <div className="officer-tile-label">Total</div>
          <div className="officer-tile-value-sm">{summary.total_cases}</div>
        </div>
        <div>
          <div className="officer-tile-label">Active</div>
          <div className="officer-tile-value-sm">{summary.active_cases}</div>
        </div>
        <div>
          <div className="officer-tile-label">Resolved</div>
          <div className="officer-tile-value-sm">{summary.resolved_cases}</div>
        </div>
        <div>
          <div className="officer-tile-label">Escalated</div>
          <div className="officer-tile-value-sm">{summary.escalated_cases}</div>
        </div>
        <div>
          <div className="officer-tile-label">Follow-up due</div>
          <div className="officer-tile-value-sm">{summary.follow_up_due}</div>
        </div>
        <div>
          <div className="officer-tile-label">Severity (L/M/H)</div>
          <div className="officer-tile-value-sm">
            {summary.severity_low}/{summary.severity_medium}/{summary.severity_high}
          </div>
        </div>
      </div>

      <h3 className="officer-section-title">Active outbreaks</h3>
      {summary.active_outbreaks.length === 0 ? (
        <p className="officer-detail-empty-text">No active outbreaks.</p>
      ) : (
        <ul className="officer-list">
          {summary.active_outbreaks.map((o, i) => (
            <li key={`${o.crop_type}-${o.disease_type}-${i}`}>
              <span
                className="tag"
                style={{
                  background: RISK_COLOR[(o.risk_level as RiskLevel) || "low"],
                  color: "#ffffff",
                }}
              >
                {RISK_LABEL[(o.risk_level as RiskLevel) || "low"]}
              </span>
              <strong>{o.disease_type}</strong> on <strong>{o.crop_type}</strong>
              <span className="officer-list-meta">
                · {o.affected_farms} farms · {o.total_cases_reported} cases reported
              </span>
            </li>
          ))}
        </ul>
      )}

      <h3 className="officer-section-title">Major crop / disease breakdown</h3>
      {summary.disease_breakdown.length === 0 ? (
        <p className="officer-detail-empty-text">No cases recorded.</p>
      ) : (
        <ul className="officer-list">
          {summary.disease_breakdown.slice(0, 5).map((e, i) => (
            <li key={`${e.crop}-${e.disease}-${i}`}>
              <span
                className="tag"
                style={{
                  background: RISK_COLOR[(e.risk_level as RiskLevel) || "medium"],
                  color: "#ffffff",
                }}
              >
                {RISK_LABEL[(e.risk_level as RiskLevel) || "medium"]}
              </span>
              <strong>{e.crop}</strong> · {e.disease}
              <span className="officer-list-meta">
                · {e.case_count} cases · {e.farm_count} farms · severity {e.severity}
              </span>
            </li>
          ))}
        </ul>
      )}

      <h3 className="officer-section-title">Intervention / feedback</h3>
      {!intv ? (
        <p className="officer-detail-empty-text">No intervention data.</p>
      ) : (
        <div className="officer-detail-grid">
          <div>
            <div className="officer-tile-label">Feedbacks</div>
            <div className="officer-tile-value-sm">{intv.total_feedbacks}</div>
          </div>
          <div>
            <div className="officer-tile-label">Treated</div>
            <div className="officer-tile-value-sm">{intv.attempted_treatment}</div>
          </div>
          <div>
            <div className="officer-tile-label">Improved</div>
            <div className="officer-tile-value-sm">{intv.crop_improved}</div>
          </div>
          <div>
            <div className="officer-tile-label">Not improved</div>
            <div className="officer-tile-value-sm">{intv.crop_not_improved}</div>
          </div>
          <div>
            <div className="officer-tile-label">No feedback yet</div>
            <div className="officer-tile-value-sm">{intv.no_feedback_yet}</div>
          </div>
        </div>
      )}

      <h3 className="officer-section-title">Risk-factor breakdown</h3>
      <div className="officer-factors-toggle">
        <label>
          <input
            type="checkbox"
            checked={includeFactors}
            onChange={(e) => onToggleFactors(e.target.checked)}
          />
          {loadingDetail ? " Reloading…" : " Show technical risk-factor breakdown"}
        </label>
      </div>
      {includeFactors && profile?.contributing_factors && (
        <table className="officer-factors">
          <thead>
            <tr>
              <th>Factor</th>
              <th>Weight</th>
              <th>Contribution</th>
              <th>Note</th>
            </tr>
          </thead>
          <tbody>
            {profile.contributing_factors.map((f) => (
              <tr key={f.name}>
                <td>{f.name}</td>
                <td>{f.weight.toFixed(1)}</td>
                <td>{f.contribution.toFixed(2)}</td>
                <td>{f.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

interface OfficerDashboardProps {
  onExit: () => void
  onExpertReview?: () => void
}

export function OfficerDashboard({ onExit, onExpertReview }: OfficerDashboardProps) {
  const [summaries, setSummaries] = useState<DistrictSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<DistrictSummary | null>(null)
  const [includeFactors, setIncludeFactors] = useState(false)
  const [loadingDetail, setLoadingDetail] = useState(false)

  // Initial overview fetch — no factors for a lightweight payload.
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getOfficerDistrictSummary(undefined, false)
      .then((data) => {
        if (cancelled) return
        setSummaries(data)
        // Auto-select the highest-risk district with data, if any.
        const ranked = [...data].filter((d) => d.risk_profile !== null)
        ranked.sort((a, b) => {
          return (b.risk_profile?.risk_score ?? 0) - (a.risk_profile?.risk_score ?? 0)
        })
        if (ranked.length > 0) setSelected(ranked[0].district)
      })
      .catch((e) => {
        if (cancelled) return
        setError(e?.message || "Failed to load district summary.")
      })
      .finally(() => {
        if (cancelled) return
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Re-fetch a single district when selected or includeFactors toggles.
  useEffect(() => {
    if (!selected) {
      setDetail(null)
      return
    }
    let cancelled = false
    setLoadingDetail(true)
    getOfficerDistrictSummary(selected, includeFactors)
      .then((data) => {
        if (cancelled) return
        setDetail(data[0] ?? null)
      })
      .catch((e) => {
        if (cancelled) return
        setError(e?.message || "Failed to load district detail.")
      })
      .finally(() => {
        if (cancelled) return
        setLoadingDetail(false)
      })
    return () => {
      cancelled = true
    }
  }, [selected, includeFactors])

  return (
    <div className="officer-dashboard">
      <div className="officer-header">
        <div>
          <div className="officer-eyebrow">SIH26131 · Officer View</div>
          <h1>Maharashtra Crop Risk Dashboard</h1>
        </div>
        <button className="small-btn" onClick={onExit} type="button">
          ← Farmer view
        </button>
        {onExpertReview && (
          <button className="small-btn" onClick={onExpertReview} type="button">
            🔬 Expert Review
          </button>
        )}
      </div>

      {loading && (
        <div className="card">
          <div className="loading">
            <div className="spinner" />
            Loading district summary…
          </div>
        </div>
      )}

      {error && <div className="error">{error}</div>}

      {!loading && !error && summaries.length > 0 && (
        <>
          <SummaryTiles summaries={summaries} />

          <div className="officer-main">
            <DistrictMap
              summaries={summaries}
              selected={selected}
              onSelect={setSelected}
            />
            <DistrictDetail
              summary={detail}
              loadingDetail={loadingDetail}
              includeFactors={includeFactors}
              onToggleFactors={setIncludeFactors}
              onClose={() => setSelected(null)}
            />
          </div>

          <div className="officer-disclaimer">
            District markers represent district-level risk (centroid coordinates).
            They are not exact farm or outbreak coordinates. Aggregated counts
            only — no farmer names, phones, or farmer IDs.
          </div>
        </>
      )}
    </div>
  )
}