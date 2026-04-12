"""Twilio SMS service for sending and receiving text messages."""

import logging
from typing import Optional

from twilio.rest import Client as TwilioClient

logger = logging.getLogger("vetflow.sms")


class SMSService:
    def __init__(self, account_sid: str, auth_token: str):
        self.client = TwilioClient(account_sid, auth_token) if account_sid else None

    async def send_sms(self, to: str, body: str, from_number: str) -> dict:
        """Send an SMS message via Twilio."""
        if not self.client:
            logger.warning("Twilio not configured, skipping SMS")
            return {"success": False, "error": "Twilio not configured"}

        try:
            message = self.client.messages.create(
                body=body,
                from_=from_number,
                to=to,
            )
            logger.info(f"SMS sent to {to}: SID={message.sid}")
            return {"success": True, "sid": message.sid}
        except Exception as e:
            logger.error(f"SMS send error: {e}")
            return {"success": False, "error": str(e)}
