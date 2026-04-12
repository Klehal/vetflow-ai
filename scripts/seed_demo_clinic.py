"""Seed a demo clinic for testing."""

import asyncio
import json
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.database import Database
from src.db.tenant_repo import TenantRepo
from src.models.tenant import Clinic, Staff


async def main():
    db = Database("data/vetflow.db")
    await db.connect()
    await db.run_migrations()

    repo = TenantRepo(db)

    clinic_id = str(uuid.uuid4())
    api_key = f"vf_demo_{uuid.uuid4().hex[:16]}"

    clinic = Clinic(
        id=clinic_id,
        name="Happy Paws Veterinary Clinic",
        phone="(512) 555-0123",
        email="info@happypawsvet.com",
        address="456 Oak Street, Austin, TX 78704",
        city="Austin",
        state="TX",
        zip_code="78704",
        timezone="America/Chicago",
        website_url="https://happypawsvet.com",
        business_hours={
            "mon": {"open": "08:00", "close": "18:00"},
            "tue": {"open": "08:00", "close": "18:00"},
            "wed": {"open": "08:00", "close": "18:00"},
            "thu": {"open": "08:00", "close": "18:00"},
            "fri": {"open": "08:00", "close": "17:00"},
            "sat": {"open": "09:00", "close": "14:00"},
            "sun": {},
        },
        services=[
            "Wellness Exams", "Vaccinations", "Dental Cleaning",
            "Spay/Neuter Surgery", "X-Rays", "Blood Work",
            "Sick Visits", "Emergency Care", "Microchipping",
        ],
        emergency_keywords=["bleeding", "seizure", "poisoning", "not breathing", "hit by car", "unconscious"],
        api_key=api_key,
        plan="standard",
        monthly_price=599.00,
    )

    await repo.create_clinic(clinic)

    # Add staff
    vet = Staff(
        id=str(uuid.uuid4()),
        clinic_id=clinic_id,
        name="Dr. Sarah Johnson",
        role="vet",
        phone="(512) 555-0124",
        email="dr.johnson@happypawsvet.com",
        is_on_call=True,
    )
    await repo.create_staff(vet)

    tech = Staff(
        id=str(uuid.uuid4()),
        clinic_id=clinic_id,
        name="Mike Chen",
        role="tech",
        phone="(512) 555-0125",
        email="mike@happypawsvet.com",
    )
    await repo.create_staff(tech)

    print(f"\nDemo clinic created!")
    print(f"  Clinic ID:  {clinic_id}")
    print(f"  API Key:    {api_key}")
    print(f"  Name:       {clinic.name}")
    print(f"\nAccess dashboard at: http://localhost:8000/dashboard/?api_key={api_key}")
    print(f"Chat widget test:    http://localhost:8000/widget/{clinic_id}/config")
    print(f"Intake form:         http://localhost:8000/intake/{clinic_id}")

    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
