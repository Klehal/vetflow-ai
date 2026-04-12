"""Appointment booking and availability management."""

import logging
import uuid
from datetime import datetime, date, timedelta
from typing import Optional

from src.db.appointment_repo import AppointmentRepo
from src.db.reminder_repo import ReminderRepo
from src.models.tenant import Clinic
from src.models.appointment import Appointment, TimeSlot
from src.models.reminder import Reminder

logger = logging.getLogger("vetflow.appointment")

SLOT_DURATION = 30  # minutes


class AppointmentService:
    def __init__(self, appt_repo: AppointmentRepo, reminder_repo: ReminderRepo):
        self.appt_repo = appt_repo
        self.reminder_repo = reminder_repo

    async def get_available_slots(self, clinic: Clinic, target_date: str, service_type: str = None) -> list[TimeSlot]:
        """Get available time slots for a given date."""
        day_name = datetime.strptime(target_date, "%Y-%m-%d").strftime("%a").lower()

        # Check for override
        override = await self.appt_repo.get_override(clinic.id, target_date)
        if override and override.is_closed:
            return []

        # Get hours for this day
        if override and override.open_time:
            open_time = override.open_time
            close_time = override.close_time
        else:
            day_hours = clinic.business_hours.get(day_name, {})
            if not day_hours or not isinstance(day_hours, dict):
                return []
            open_time = day_hours.get("open")
            close_time = day_hours.get("close")

        if not open_time or not close_time:
            return []

        # Generate all possible slots
        slots = []
        current = datetime.strptime(f"{target_date} {open_time}", "%Y-%m-%d %H:%M")
        end = datetime.strptime(f"{target_date} {close_time}", "%Y-%m-%d %H:%M")

        while current + timedelta(minutes=SLOT_DURATION) <= end:
            slots.append(TimeSlot(
                date=target_date,
                time=current.strftime("%H:%M"),
                duration_minutes=SLOT_DURATION,
                available=True,
            ))
            current += timedelta(minutes=SLOT_DURATION)

        # Mark booked slots as unavailable
        existing = await self.appt_repo.get_appointments_by_date(clinic.id, target_date)
        booked_times = {a.scheduled_time for a in existing}

        for slot in slots:
            if slot.time in booked_times:
                slot.available = False

        return slots

    async def book_appointment(
        self,
        clinic: Clinic,
        owner_name: str,
        pet_name: str,
        service_type: str,
        target_date: str,
        target_time: str,
        owner_phone: str = None,
        owner_email: str = None,
        pet_species: str = None,
        notes: str = None,
        source: str = "chat",
    ) -> dict:
        """Book an appointment. Returns success/error dict."""
        # Check availability
        slots = await self.get_available_slots(clinic, target_date)
        available_times = {s.time for s in slots if s.available}

        if target_time not in available_times:
            return {
                "success": False,
                "error": f"The {target_time} slot on {target_date} is not available.",
                "available_times": sorted(available_times)[:5],
            }

        appt = Appointment(
            id=str(uuid.uuid4()),
            clinic_id=clinic.id,
            owner_name=owner_name,
            owner_phone=owner_phone,
            owner_email=owner_email,
            pet_name=pet_name,
            pet_species=pet_species,
            service_type=service_type,
            scheduled_date=target_date,
            scheduled_time=target_time,
            source=source,
            notes=notes,
        )

        await self.appt_repo.create_appointment(appt)
        logger.info(f"Booked appointment {appt.id}: {pet_name} ({service_type}) at {target_date} {target_time}")

        # Schedule reminders
        appt_dt = datetime.strptime(f"{target_date} {target_time}", "%Y-%m-%d %H:%M")

        for hours_before, reminder_type in [(48, "appointment_48h"), (24, "appointment_24h")]:
            remind_at = appt_dt - timedelta(hours=hours_before)
            if remind_at > datetime.now():
                reminder = Reminder(
                    id=str(uuid.uuid4()),
                    clinic_id=clinic.id,
                    type=reminder_type,
                    appointment_id=appt.id,
                    recipient_phone=owner_phone,
                    recipient_email=owner_email,
                    channel="sms" if owner_phone else "email",
                    scheduled_for=remind_at.isoformat(),
                )
                await self.reminder_repo.create_reminder(reminder)

        return {
            "success": True,
            "appointment_id": appt.id,
            "message": f"Appointment booked for {pet_name} on {target_date} at {target_time} for {service_type}.",
        }

    async def cancel_appointment(self, appt_id: str) -> dict:
        appt = await self.appt_repo.get_appointment(appt_id)
        if not appt:
            return {"success": False, "error": "Appointment not found"}
        await self.appt_repo.cancel_appointment(appt_id)
        return {"success": True, "message": "Appointment cancelled"}
