"""CRUD operations for reminders and vaccination records."""

from typing import Optional
from src.db.database import Database
from src.models.reminder import Reminder, VaccinationRecord


class ReminderRepo:
    def __init__(self, db: Database):
        self.db = db

    async def create_reminder(self, reminder: Reminder) -> Reminder:
        await self.db.execute(
            """INSERT INTO reminders (id, clinic_id, type, appointment_id, pet_id,
                recipient_phone, recipient_email, channel, scheduled_for, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (reminder.id, reminder.clinic_id, reminder.type, reminder.appointment_id,
             reminder.pet_id, reminder.recipient_phone, reminder.recipient_email,
             reminder.channel, reminder.scheduled_for, reminder.status),
        )
        return reminder

    async def get_pending_reminders(self, before_time: str) -> list[Reminder]:
        rows = await self.db.fetch_all(
            "SELECT * FROM reminders WHERE status = 'pending' AND scheduled_for <= ? ORDER BY scheduled_for",
            (before_time,),
        )
        return [Reminder.from_row(r) for r in rows]

    async def mark_sent(self, reminder_id: str):
        await self.db.execute(
            "UPDATE reminders SET status = 'sent', sent_at = CURRENT_TIMESTAMP WHERE id = ?",
            (reminder_id,),
        )

    async def mark_failed(self, reminder_id: str, error: str):
        await self.db.execute(
            "UPDATE reminders SET status = 'failed', error_message = ? WHERE id = ?",
            (error, reminder_id),
        )

    async def create_vaccination(self, record: VaccinationRecord) -> VaccinationRecord:
        await self.db.execute(
            """INSERT INTO vaccination_records (id, clinic_id, pet_id, vaccine_name,
                administered_date, next_due_date, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (record.id, record.clinic_id, record.pet_id, record.vaccine_name,
             record.administered_date, record.next_due_date, record.notes),
        )
        return record

    async def get_vaccinations_due(self, clinic_id: str, before_date: str) -> list[VaccinationRecord]:
        rows = await self.db.fetch_all(
            "SELECT * FROM vaccination_records WHERE clinic_id = ? AND next_due_date <= ? ORDER BY next_due_date",
            (clinic_id, before_date),
        )
        return [VaccinationRecord.from_row(r) for r in rows]
