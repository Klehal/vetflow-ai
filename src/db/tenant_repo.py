"""CRUD operations for clinics and staff."""

import json
import uuid
from typing import Optional

from src.db.database import Database
from src.models.tenant import Clinic, Staff


class TenantRepo:
    def __init__(self, db: Database):
        self.db = db

    async def create_clinic(self, clinic: Clinic) -> Clinic:
        await self.db.execute(
            """INSERT INTO clinics (id, name, phone, email, address, city, state, zip_code,
                timezone, website_url, business_hours, services, emergency_keywords,
                bland_agent_id, twilio_phone, widget_primary_color, widget_greeting,
                api_key, is_active, plan, monthly_price)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (clinic.id, clinic.name, clinic.phone, clinic.email, clinic.address,
             clinic.city, clinic.state, clinic.zip_code, clinic.timezone,
             clinic.website_url, json.dumps(clinic.business_hours),
             json.dumps(clinic.services), json.dumps(clinic.emergency_keywords),
             clinic.bland_agent_id, clinic.twilio_phone, clinic.widget_primary_color,
             clinic.widget_greeting, clinic.api_key, int(clinic.is_active),
             clinic.plan, clinic.monthly_price),
        )
        return clinic

    async def get_clinic_by_id(self, clinic_id: str) -> Optional[Clinic]:
        row = await self.db.fetch_one("SELECT * FROM clinics WHERE id = ?", (clinic_id,))
        return Clinic.from_row(row) if row else None

    async def get_clinic_by_api_key(self, api_key: str) -> Optional[Clinic]:
        row = await self.db.fetch_one("SELECT * FROM clinics WHERE api_key = ? AND is_active = 1", (api_key,))
        return Clinic.from_row(row) if row else None

    async def get_clinic_by_twilio_phone(self, phone: str) -> Optional[Clinic]:
        row = await self.db.fetch_one("SELECT * FROM clinics WHERE twilio_phone = ?", (phone,))
        return Clinic.from_row(row) if row else None

    async def get_all_active_clinics(self) -> list[Clinic]:
        rows = await self.db.fetch_all("SELECT * FROM clinics WHERE is_active = 1")
        return [Clinic.from_row(r) for r in rows]

    async def update_clinic(self, clinic_id: str, **kwargs):
        if "business_hours" in kwargs:
            kwargs["business_hours"] = json.dumps(kwargs["business_hours"])
        if "services" in kwargs:
            kwargs["services"] = json.dumps(kwargs["services"])
        if "emergency_keywords" in kwargs:
            kwargs["emergency_keywords"] = json.dumps(kwargs["emergency_keywords"])

        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [clinic_id]
        await self.db.execute(
            f"UPDATE clinics SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            tuple(vals),
        )

    async def create_staff(self, staff: Staff) -> Staff:
        await self.db.execute(
            "INSERT INTO staff (id, clinic_id, name, role, phone, email, is_on_call) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (staff.id, staff.clinic_id, staff.name, staff.role, staff.phone, staff.email, int(staff.is_on_call)),
        )
        return staff

    async def get_on_call_staff(self, clinic_id: str) -> Optional[Staff]:
        row = await self.db.fetch_one(
            "SELECT * FROM staff WHERE clinic_id = ? AND is_on_call = 1 LIMIT 1", (clinic_id,)
        )
        return Staff.from_row(row) if row else None

    async def get_staff_by_clinic(self, clinic_id: str) -> list[Staff]:
        rows = await self.db.fetch_all("SELECT * FROM staff WHERE clinic_id = ?", (clinic_id,))
        return [Staff.from_row(r) for r in rows]
