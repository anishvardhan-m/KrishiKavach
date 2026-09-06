"""Seed script for KrishiKavach demo data.

Run with: python -m scripts.seed_data

Populates the database with:
- Demo farmers and farms
- Sample disease reports (outbreak data)
- Weather context data from CSV files
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from uuid import uuid4

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import get_sync_session_cm, init_db
from app.models import (
    Farmer, Farm, DiseaseReport, WeatherContext,
    Expert, Case, CaseFeedback,
)


MAHARASHTRA_DISTRICTS = [
    "Ahmednagar", "Akola", "Amravati", "Aurangabad", "Beed",
    "Bidar", "Buldhana", "Chandrapur", "Dhule", "Gadchiroli",
    "Gondia", "Hingoli", "Jalgaon", "Jalna", "Kolhapur",
    "Latur", "Mumbai City", "Mumbai Suburban", "Nagpur", "Nanded",
    "Nandurbar", "Nashik", "Osmanabad", "Palghar", "Parbhani",
    "Pune", "Raigad", "Ratnagiri", "Sangli", "Satara",
    "Sindhudurg", "Solapur", "Thane", "Wardha", "Washim", "Yavatmal",
]

# Demo disease reports (seeded outbreak data)
DEMO_DISEASE_REPORTS = [
    {"district": "Pune", "crop": "Tomato", "disease": "Late Blight", "risk": "high", "farms": 12, "cases": 34},
    {"district": "Nashik", "crop": "Onion", "disease": "Purple Blotch", "risk": "medium", "farms": 8, "cases": 19},
    {"district": "Aurangabad", "crop": "Cotton", "disease": "Bollworm", "risk": "critical", "farms": 45, "cases": 127},
    {"district": "Solapur", "crop": "Grapes", "disease": "Downy Mildew", "risk": "medium", "farms": 6, "cases": 14},
    {"district": "Kolhapur", "crop": "Sugarcane", "disease": "Red Rot", "risk": "high", "farms": 22, "cases": 58},
    {"district": "Nagpur", "crop": "Orange", "disease": "Citrus Greening", "risk": "high", "farms": 15, "cases": 41},
    {"district": "Satara", "crop": "Tomato", "disease": "Early Blight", "risk": "medium", "farms": 9, "cases": 23},
    {"district": "Ahmednagar", "crop": "Grapes", "disease": "Powdery Mildew", "risk": "low", "farms": 4, "cases": 8},
]

DEMO_EXPERTS = [
    {"name": "Dr. Prakash Ghadge", "specialty": "Tomato & Vegetable Crops", "email": "prakash.ghadge@agri.mah.nic.in"},
    {"name": "Dr. Sunanda Pawar", "specialty": "Cotton & Pulses", "email": "sunanda.pawar@agri.mah.nic.in"},
    {"name": "Dr. Ramesh Kulkarni", "specialty": "Grape & Orchard Crops", "email": "ramesh.kulkarni@agri.mah.nic.in"},
]


def load_weather_contexts(session, limit: int = 100):
    """Load recent weather data from CSV files."""
    data_dir = Path(__file__).resolve().parent.parent.parent / "data"

    soil_path = data_dir / "soil_moisture.csv"
    evapo_path = data_dir / "evapotranspiration.csv"

    if not soil_path.exists() or not evapo_path.exists():
        print(f"  [SKIP] CSV files not found at {data_dir}")
        return 0

    # Read evapotranspiration (smaller file)
    evapo_by_district = {}
    with open(evapo_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dist = row.get("DistrictName", "").strip()
            evapo_by_district[dist] = {
                "evapo_mm": float(row.get("Evapo Level (mm)", 0) or 0),
                "aggregate_evapo": float(row.get("Aggregate Evapo Level (mm)", 0) or 0),
            }

    # Read soil moisture
    count = 0
    with open(soil_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dist = row.get("DistrictName", "").strip()
            if not dist or dist not in MAHARASHTRA_DISTRICTS:
                continue

            moisture = float(row.get("Volume Soilmoisture percg (at 15cm)", 0) or 0)
            evapo = evapo_by_district.get(dist, {})

            wc = WeatherContext(
                district=dist,
                state="Maharashtra",
                soil_moisture_percent=round(moisture, 2),
                evapotranspiration_mm=round(evapo.get("evapo_mm", 0), 3),
                recorded_at=datetime.now(),
                source="soil_moisture_csv",
            )
            session.add(wc)
            count += 1
            if count >= limit:
                break

    return count


def seed_disease_reports(session):
    """Seed disease outbreak reports."""
    today = date.today()
    count = 0
    for report in DEMO_DISEASE_REPORTS:
        dr = DiseaseReport(
            district=report["district"],
            state="Maharashtra",
            crop_type=report["crop"],
            disease_type=report["disease"],
            risk_level=report["risk"],
            affected_farms=report["farms"],
            total_cases_reported=report["cases"],
            confirmed_cases=int(report["cases"] * 0.6),
            valid_from=today - timedelta(days=14),
            valid_to=today + timedelta(days=14),
            source_cases=report["cases"],
        )
        session.add(dr)
        count += 1
    return count


def seed_experts(session):
    """Seed demo experts."""
    count = 0
    for exp in DEMO_EXPERTS:
        expert = Expert(
            name=exp["name"],
            specialty=exp["specialty"],
            contact_email=exp["email"],
            is_active=True,
        )
        session.add(expert)
        count += 1
    return count


def seed_demo_farmers(session):
    """Seed demo farmers and farms."""
    demo_farmers = [
        {"name": "Ramesh Patil", "village": "Pirangut", "district": "Pune", "phone": "+919876543210", "crop": "Tomato"},
        {"name": "Sunita Jadhav", "village": "Shirur", "district": "Pune", "phone": "+919876543211", "crop": "Grapes"},
        {"name": "Anna More", "village": "Baramati", "district": "Pune", "phone": "+919876543212", "crop": "Onion"},
        {"name": "Vijay Shinde", "village": "Indapur", "district": "Pune", "phone": "+919876543213", "crop": "Sugarcane"},
    ]

    count = 0
    for f_data in demo_farmers:
        farmer = Farmer(
            name=f_data["name"],
            phone=f_data["phone"],
            village=f_data["village"],
            district=f_data["district"],
            state="Maharashtra",
            primary_language="marathi",
        )
        session.add(farmer)
        session.flush()  # Get ID

        farm = Farm(
            farmer_id=farmer.id,
            primary_crop=f_data["crop"],
            area_hectares=round(1.0 + count * 0.5, 1),
            location_point=f"SRID=4326;POINT({73.0 + count * 0.1:.4f} {18.5 + count * 0.05:.4f})",
        )
        session.add(farm)
        count += 1

    return count


def run_seed():
    """Run the full seed operation."""
    print("KrishiKavach Seed Script")
    print("=" * 50)

    print("\n[1/4] Initializing database schema...")
    import asyncio
    asyncio.run(init_db())
    print("  OK - schema ready")

    print("\n[2/4] Seeding farmers and farms...")
    with get_sync_session_cm() as session:
        n = seed_demo_farmers(session)
        print(f"  OK - {n} farmers + farms seeded")

    print("\n[3/4] Seeding disease outbreak reports...")
    with get_sync_session_cm() as session:
        n = seed_disease_reports(session)
        print(f"  OK - {n} disease reports seeded")

    print("\n[4/4] Seeding experts...")
    with get_sync_session_cm() as session:
        n = seed_experts(session)
        print(f"  OK - {n} experts seeded")

    print("\n[5/5] Loading weather contexts from CSV (up to 100 rows)...")
    with get_sync_session_cm() as session:
        n = load_weather_contexts(session, limit=100)
        print(f"  OK - {n} weather context records loaded")

    print("\n" + "=" * 50)
    print("Seed complete! Demo data is ready.")
    print("\nDemo farmers: Ramesh Patil, Sunita Jadhav, Anna More, Vijay Shinde")
    print("Demo districts: Pune, Nashik, Aurangabad, Solapur, Kolhapur, Nagpur, Satara, Ahmednagar")


if __name__ == "__main__":
    run_seed()
