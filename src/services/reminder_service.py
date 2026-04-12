"""Reminder dispatch service — checks for pending reminders and sends them."""

import logging
from datetime import datetime

from src.db.reminder_repo import ReminderRepo
from src.db.appointment_repo import AppointmentRepo
from src.services.sms_service import SMSService
from src.services.email_service import EmailService

logger = logging.getLogger("vetflow.reminders")


class ReminderService:
    def __init__(self, reminder_repo: ReminderRepo, appt_repo: AppointmentRepo,
                 sms_service: SMSService, email_service: EmailService):
        self.reminder_repo = reminder_repo
        self.appt_repo = appt_repo
        self.sms = sms_service
        self.email = email_service

    async def process_pending_reminders(self, twilio_numbers: dict = None):
        """Check and send all pending reminders that are due."""
        now = datetime.now().isoformat()
        pending = await self.reminder_repo.get_pending_reminders(now)

        logger.info(f"Processing {len(pending)} pending reminders")
        sent = 0
        failed = 0

        for reminder in pending:
            try:
                appt = await self.appt_repo.get_appointment(reminder.appointment_id) if reminder.appointment_id else None

                if appt and appt.status == "cancelled":
                    await self.reminder_repo.mark_sent(reminder.id)  # Skip cancelled
                    continue

                # Build message
                if appt:
                    msg = (
                        f"Hi! This is a reminder from your vet clinic about your appointment "
                        f"for {appt.pet_name} on {appt.scheduled_date} at {appt.scheduled_time} "
                        f"for {appt.service_type}. Reply CONFIRM to confirm or CANCEL to cancel."
                    )
                    subject = f"Appointment Reminder for {appt.pet_name}"
                else:
                    msg = "You have an upcoming reminder from your vet clinic. Please call us for details."
                    subject = "Reminder from your vet clinic"

                # Send via appropriate channel
                if reminder.channel in ("sms", "both") and reminder.recipient_phone:
                    from_number = (twilio_numbers or {}).get(reminder.clinic_id, "")
                    if from_number:
                        result = await self.sms.send_sms(reminder.recipient_phone, msg, from_number)
                        if not result["success"]:
                            raise Exception(result["error"])

                if reminder.channel in ("email", "both") and reminder.recipient_email:
                    html = f"<p>{msg}</p>"
                    result = await self.email.send_email(reminder.recipient_email, subject, html, msg)
                    if not result["success"]:
                        raise Exception(result["error"])

                await self.reminder_repo.mark_sent(reminder.id)
                if appt:
                    await self.appt_repo.mark_reminder_sent(appt.id, reminder.type)
                sent += 1

            except Exception as e:
                logger.error(f"Failed to send reminder {reminder.id}: {e}")
                await self.reminder_repo.mark_failed(reminder.id, str(e))
                failed += 1

        logger.info(f"Reminders processed: {sent} sent, {failed} failed")
        return {"sent": sent, "failed": failed}
