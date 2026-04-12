"""CRUD operations for appointments and availability."""

from typing import Optional
from src.db.database import Database
from src.models.appointment import Appointment, AvailabilityOverride


class AppointmentRepo:
    def __init__(self, db: Database):
        self.db = db

    async def create_appointment(self, appt: Appointment) -> Appointment:
        await self.db.execute(
            """INSERT INTO appointments (id, clinic_id, pet_id, owner_name, owner_phone,
                owner_email, pet_name, pet_species, service_type, scheduled_date,
                scheduled_time, duration_minutes, status, source, notes, staff_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (appt.id, appt.clinic_id, appt.pet_id, appt.owner_name, appt.owner_phone,
             appt.owner_email, appt.pet_name, appt.pet_species, appt.service_type,
             appt.scheduled_date, appt.scheduled_time, appt.duration_minutes,
             appt.status, appt.source, appt.notes, appt.staff_id),
        )
        return appt

    async def get_appointment(self, appt_id: str) -> Optional[Appointment]:
        row = await self.db.fetch_one("SELECT * FROM appointments WHERE id = ?", (appt_id,))
        return Appointment.from_row(row) if row else None

    async def get_appointments_by_date(self, clinic_id: str, date: str) -> list[Appointment]:
        rows = await self.db.fetch_all(
            "SELECT * FROM appointments WHERE clinic_id = ? AND scheduled_date = ? AND status != 'cancelled' ORDER BY scheduled_time",
            (clinic_id, date),
        )
        return [Appointment.from_row(r) for r in rows]

    async def get_appointments_range(self, clinic_id: str, start_date: str, end_date: str) -> list[Appointment]:
        rows = await self.db.fetch_all(
            """SELECT * FROM appointments WHERE clinic_id = ? AND scheduled_date BETWEEN ? AND ?
               AND status != 'cancelled' ORDER BY scheduled_date, scheduled_time""",
            (clinic_id, start_date, end_date),
        )
        return [Appointment.from_row(r) for r in rows]

    async def cancel_appointment(self, appt_id: str):
        await self.db.execute(
            "UPDATE appointments SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (appt_id,),
        )

    async def mark_reminder_sent(self, appt_id: str, reminder_type: str):
        col = "reminder_48h_sent" if "48" in reminder_type else "reminder_24h_sent"
        await self.db.execute(
            f"UPDATE appointments SET {col} = 1 WHERE id = ?", (appt_id,),
        )

    async def get_upcoming_needing_reminder(self, clinic_id: str, min_time: str, max_time: str, reminder_col: str) -> list[Appointment]:
        rows = await self.db.fetch_all(
            f"""SELECT * FROM appointments
                WHERE clinic_id = ? AND status = 'confirmed'
                AND datetime(scheduled_date || ' ' || scheduled_time) BETWEEN ? AND ?
                AND {reminder_col} = 0""",
            (clinic_id, min_time, max_time),
        )
        return [Appointment.from_row(r) for r in rows]

    async def get_override(self, clinic_id: str, date: str) -> Optional[AvailabilityOverride]:
        row = await self.db.fetch_one(
            "SELECT * FROM availability_overrides WHERE clinic_id = ? AND override_date = ?",
            (clinic_id, date),
        )
        return AvailabilityOverride.from_row(row) if row else None
