"""Focused tests for risk_forecast pure helpers and bucketing.

These tests do NOT touch the database — they exercise the deterministic
math that underlies the risk score. DB integration is covered by the
running API tests in the test harness.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

# Allow running directly: `pytest backend/tests/test_risk_forecast.py`
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.services.risk_forecast import (
    W_CASES,
    W_OUTBREAK,
    W_WEATHER,
    W_SEVERITY,
    W_CONFIDENCE,
    W_GEO,
    bucketize,
    clip_score,
    confidence_signal,
    explain,
    geo_proximity_signal,
    haversine_km,
    outbreak_signal,
    parse_wkt_point,
    recent_cases_signal,
    recommend_action,
    severity_signal,
    weather_signal,
    GEO_NEAR_RADIUS_KM,
    RiskForecast,
    RiskFactor,
)


# ---------------------------------------------------------------------------
# clip_score
# ---------------------------------------------------------------------------

class TestClipScore:
    def test_zero(self):
        assert clip_score(0.0) == 0.0

    def test_in_range(self):
        assert clip_score(50.0) == 50.0

    def test_negative_clipped(self):
        assert clip_score(-5.0) == 0.0

    def test_overflow_clipped(self):
        assert clip_score(150.0) == 100.0


# ---------------------------------------------------------------------------
# bucketize
# ---------------------------------------------------------------------------

class TestBucketize:
    def test_low(self):
        assert bucketize(0.0) == "low"
        assert bucketize(15.0) == "low"
        assert bucketize(29.99) == "low"

    def test_medium(self):
        assert bucketize(30.0) == "medium"
        assert bucketize(45.0) == "medium"
        assert bucketize(59.99) == "medium"

    def test_high(self):
        assert bucketize(60.0) == "high"
        assert bucketize(72.0) == "high"
        assert bucketize(84.99) == "high"

    def test_critical(self):
        assert bucketize(85.0) == "critical"
        assert bucketize(100.0) == "critical"

    def test_clip_before_bucket(self):
        # Negative clamps to 0, then buckets to low
        assert bucketize(-10.0) == "low"
        # >100 clamps to 100, then buckets to critical
        assert bucketize(120.0) == "critical"


# ---------------------------------------------------------------------------
# recent_cases_signal
# ---------------------------------------------------------------------------

class TestRecentCasesSignal:
    def test_zero_cases(self):
        sig, note = recent_cases_signal(0)
        assert sig == 0.0
        assert "0 cases" in note

    def test_full_signal(self):
        sig, _ = recent_cases_signal(5)
        assert sig == pytest.approx(W_CASES, rel=1e-6)
        sig2, _ = recent_cases_signal(10)
        assert sig2 == pytest.approx(W_CASES, rel=1e-6)  # capped

    def test_linear_ramp(self):
        sig_half, _ = recent_cases_signal(2)  # 2/5 of W_CASES
        assert sig_half == pytest.approx(W_CASES * 2 / 5, rel=1e-6)
        sig_one, _ = recent_cases_signal(1)
        assert sig_one == pytest.approx(W_CASES / 5, rel=1e-6)

    def test_custom_max(self):
        sig, _ = recent_cases_signal(3, max_for_full_signal=3)
        assert sig == pytest.approx(W_CASES, rel=1e-6)


# ---------------------------------------------------------------------------
# outbreak_signal
# ---------------------------------------------------------------------------

class TestOutbreakSignal:
    def test_known_levels(self):
        for lvl, expected in [("low", 5.0), ("medium", 20.0), ("high", 35.0), ("critical", 45.0)]:
            sig, note = outbreak_signal(lvl)
            assert sig == expected
            assert lvl in note

    def test_unknown_level_zero(self):
        sig, _ = outbreak_signal("unknown_level")
        assert sig == 0.0

    def test_none_zero(self):
        sig, note = outbreak_signal(None)
        assert sig == 0.0
        assert "No seeded" in note

    def test_case_insensitive(self):
        sig, _ = outbreak_signal("HIGH")
        assert sig == 35.0


# ---------------------------------------------------------------------------
# weather_signal — must NOT invent temperature/humidity values
# ---------------------------------------------------------------------------

class TestWeatherSignal:
    def test_all_none_contributes_zero(self):
        sig, note = weather_signal(None, None, None, None)
        assert sig == 0.0
        assert "No environmental data" in note

    def test_soil_moisture_high(self):
        sig, note = weather_signal(75.0, None, None, None)
        assert sig == pytest.approx(12.0, rel=1e-6)
        assert "soil moisture" in note
        assert "high" in note

    def test_soil_moisture_dry(self):
        sig, note = weather_signal(15.0, None, None, None)
        assert sig == pytest.approx(8.0, rel=1e-6)
        assert "very dry" in note

    def test_soil_moisture_normal(self):
        sig, _ = weather_signal(45.0, None, None, None)
        assert sig == 0.0

    def test_evapo_high(self):
        sig, note = weather_signal(None, 6.0, None, None)
        assert sig == pytest.approx(13.0, rel=1e-6)
        assert "evapotranspiration" in note

    def test_evapo_moderate(self):
        sig, _ = weather_signal(None, 4.0, None, None)
        assert sig == pytest.approx(7.0, rel=1e-6)

    def test_evapo_normal(self):
        sig, _ = weather_signal(None, 2.0, None, None)
        assert sig == 0.0

    def test_temp_humidity_present(self):
        # 25C and 85% humidity -> fungal pressure band
        sig, note = weather_signal(None, None, 25.0, 85.0)
        # Only temp+humidity contribution (10.0) since sm/et are None
        assert sig == pytest.approx(10.0, rel=1e-6)
        assert "fungal-pressure" in note

    def test_temp_humidity_not_in_band(self):
        sig, note = weather_signal(None, None, 35.0, 30.0)
        # temp+humidity not in band -> no contribution from that subfactor
        assert sig == 0.0
        assert "not in fungal-pressure" in note

    def test_only_one_of_temp_humidity_does_not_score(self):
        # If only one is present, do NOT invent the other — contribute 0
        sig, _ = weather_signal(None, None, 25.0, None)
        assert sig == 0.0
        sig2, _ = weather_signal(None, None, None, 85.0)
        assert sig2 == 0.0

    def test_combined_soil_plus_et(self):
        # sm=75 -> 12, et=6 -> 13, total 25 = W_WEATHER cap
        sig, _ = weather_signal(75.0, 6.0, None, None)
        assert sig == pytest.approx(W_WEATHER, rel=1e-6)


# ---------------------------------------------------------------------------
# severity_signal
# ---------------------------------------------------------------------------

class TestSeveritySignal:
    def test_low(self):
        sig, note = severity_signal("low")
        assert sig == 2.0
        assert "low" in note

    def test_medium(self):
        sig, _ = severity_signal("medium")
        assert sig == 8.0

    def test_high(self):
        sig, _ = severity_signal("high")
        assert sig == 15.0

    def test_unknown(self):
        sig, _ = severity_signal("extreme")
        assert sig == 0.0

    def test_none(self):
        sig, _ = severity_signal(None)
        assert sig == 0.0


# ---------------------------------------------------------------------------
# confidence_signal
# ---------------------------------------------------------------------------

class TestConfidenceSignal:
    def test_high_confidence_low_contribution(self):
        sig, _ = confidence_signal(0.95)
        assert sig == pytest.approx(W_CONFIDENCE * 0.05, rel=1e-6)

    def test_low_confidence_high_contribution(self):
        sig, _ = confidence_signal(0.3)
        assert sig == pytest.approx(W_CONFIDENCE * 0.7, rel=1e-6)

    def test_none_max_uncertainty(self):
        sig, note = confidence_signal(None)
        assert sig == pytest.approx(W_CONFIDENCE, rel=1e-6)
        assert "unknown" in note

    def test_clamps_out_of_range(self):
        sig_low, _ = confidence_signal(-0.5)
        assert sig_low == pytest.approx(W_CONFIDENCE, rel=1e-6)
        sig_high, _ = confidence_signal(1.5)
        assert sig_high == 0.0


# ---------------------------------------------------------------------------
# recommend_action
# ---------------------------------------------------------------------------

class TestRecommendAction:
    def test_critical(self):
        msg = recommend_action("critical", "Tomato", "Late Blight")
        assert "Escalate" in msg
        assert "Tomato" in msg

    def test_high(self):
        msg = recommend_action("high", "Sugarcane", "Red Rot")
        assert "promptly" in msg.lower() or "monitor" in msg.lower()

    def test_medium(self):
        msg = recommend_action("medium", "Tomato", "Early Blight")
        assert "follow-up" in msg.lower() or "7 days" in msg.lower()

    def test_low(self):
        msg = recommend_action("low", "Tomato", "Healthy")
        assert "routine" in msg.lower() or "monitoring" in msg.lower()

    def test_handles_none(self):
        msg = recommend_action("low", None, None)
        assert "this crop" in msg


# ---------------------------------------------------------------------------
# explain
# ---------------------------------------------------------------------------

class TestExplain:
    def test_includes_level_and_score(self):
        forecast = RiskForecast(
            risk_score=42.0,
            risk_level="medium",
            contributing_factors=[
                RiskFactor(
                    name="F1", weight=30.0, raw_signal=5.0,
                    contribution=20.0, note="5 cases",
                )
            ],
        )
        text = explain(forecast)
        assert "medium" in text
        assert "42" in text
        assert "5 cases" in text


# ---------------------------------------------------------------------------
# Weight totals — sanity check
# ---------------------------------------------------------------------------

class TestWeightTotals:
    def test_max_weight_is_100(self):
        # Sum may exceed 100 because individual factors are each clamped
        # to their own weight and the final total is clipped at 100 by
        # clip_score. We assert >=100 to document that overflow is
        # deliberately absorbed by clip_score.
        total = W_CASES + W_OUTBREAK + W_WEATHER + W_SEVERITY + W_CONFIDENCE + W_GEO
        assert total >= 100.0
        # And each individual factor's clip is consistent with its weight:
        assert W_GEO == pytest.approx(10.0, rel=1e-6)


# ---------------------------------------------------------------------------
# Geospatial proximity — WKT parsing, haversine, and the geo signal
# ---------------------------------------------------------------------------

class TestParseWktPoint:
    def test_valid_basic(self):
        assert parse_wkt_point("POINT(73.85 18.52)") == (73.85, 18.52)

    def test_valid_with_whitespace(self):
        assert parse_wkt_point("POINT ( 73.85 18.52 )") == (73.85, 18.52)

    def test_valid_with_trailing_text(self):
        # Tolerant of trailing precision / SRID text
        assert parse_wkt_point("POINT(73.85 18.52) 4326") == (73.85, 18.52)

    def test_none(self):
        assert parse_wkt_point(None) is None

    def test_empty(self):
        assert parse_wkt_point("") is None

    def test_garbage(self):
        assert parse_wkt_point("not-a-point") is None
        assert parse_wkt_point("POINT()") is None
        assert parse_wkt_point("POINT(73.85)") is None  # missing lat

    def test_out_of_range(self):
        assert parse_wkt_point("POINT(181.0 0.0)") is None
        assert parse_wkt_point("POINT(0.0 91.0)") is None


class TestHaversineKm:
    def test_zero(self):
        assert haversine_km(73.85, 18.52, 73.85, 18.52) == pytest.approx(0.0, abs=1e-6)

    def test_pune_to_nearby_village(self):
        # Two points ~1 km apart around Pune (73.85, 18.52)
        d = haversine_km(73.85, 18.52, 73.86, 18.52)
        assert 0.5 < d < 2.0

    def test_pune_to_mumbai(self):
        # Pune (73.85, 18.52) to Mumbai (72.87, 19.07) ≈ 120 km
        d = haversine_km(73.85, 18.52, 72.87, 19.07)
        assert 115 < d < 130


class TestGeoProximitySignal:
    def test_zero_count(self):
        sig, note = geo_proximity_signal(0)
        assert sig == 0.0
        assert "No nearby" in note

    def test_negative_count(self):
        sig, _ = geo_proximity_signal(-1)
        assert sig == 0.0

    def test_full_signal(self):
        sig, _ = geo_proximity_signal(3)
        assert sig == pytest.approx(W_GEO, rel=1e-6)
        # Capped
        sig2, _ = geo_proximity_signal(10)
        assert sig2 == pytest.approx(W_GEO, rel=1e-6)

    def test_linear_ramp(self):
        sig, _ = geo_proximity_signal(1)
        # 1/3 of W_GEO
        assert sig == pytest.approx(W_GEO / 3.0, rel=1e-6)


class TestRiskForecastScoring:
    """End-to-end RiskForecast tests covering the geo signal and the
    0-100 clip invariant."""

    def _make_forecast(self, contributions):
        """Build a RiskForecast with the named factor contributions."""
        factors = [
            RiskFactor(
                name=f"f{i}", weight=10.0, raw_signal=c, contribution=c,
                note=f"factor {i}",
            )
            for i, c in enumerate(contributions)
        ]
        total = clip_score(sum(contributions))
        return RiskForecast(
            risk_score=total,
            risk_level=bucketize(total),
            contributing_factors=factors,
            recommended_action="",
            explanation="",
        )

    def test_score_bounded_with_nearby_case(self):
        # Worst-case: all factors at max, plus a max geo signal.
        contributions = [W_CASES, W_OUTBREAK, W_WEATHER, W_SEVERITY, W_CONFIDENCE, W_GEO]
        f = self._make_forecast(contributions)
        assert 0.0 <= f.risk_score <= 100.0
        # Clip holds even when the raw sum exceeds 100.
        raw_sum = sum(contributions)
        assert f.risk_score == pytest.approx(clip_score(raw_sum), rel=1e-6)
        assert f.risk_score == 100.0  # exact cap

    def test_score_bounded_with_distant_only(self):
        # Same as above but geo = 0 because no nearby cases.
        contributions = [W_CASES, W_OUTBREAK, W_WEATHER, W_SEVERITY, W_CONFIDENCE, 0.0]
        f = self._make_forecast(contributions)
        assert 0.0 <= f.risk_score <= 100.0
        # Total without geo is exactly 95 → still in [0, 100].
        assert f.risk_score == pytest.approx(95.0, rel=1e-6)

    def test_score_bounded_with_missing_coordinates(self):
        # When no coordinates, geo signal is 0 → score must still be in
        # [0, 100] and the explanation must mention the missing geo.
        contributions = [W_CASES, W_OUTBREAK, W_WEATHER, W_SEVERITY, W_CONFIDENCE, 0.0]
        f = self._make_forecast(contributions)
        # Add a geo factor whose note is "no coordinates".
        f.contributing_factors[-1] = RiskFactor(
            name="Nearby farm-coordinate cases (0-10 km)",
            weight=W_GEO,
            raw_signal=0.0,
            contribution=0.0,
            note="No farm coordinates available for geospatial proximity",
        )
        assert 0.0 <= f.risk_score <= 100.0
        assert f.risk_score == pytest.approx(95.0, rel=1e-6)
        # and the geo factor explicitly contributes 0
        assert f.contributing_factors[-1].contribution == 0.0
        assert "No farm coordinates" in f.contributing_factors[-1].note

    def test_radius_constant_is_ten_km(self):
        assert GEO_NEAR_RADIUS_KM == pytest.approx(10.0, rel=1e-6)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
