"""SendGrid email service for reminders and notifications."""

import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

logger = logging.getLogger("vetflow.email")


class EmailService:
    def __init__(self, api_key: str, from_email: str = "hello@vetflow.ai", from_name: str = "VetFlow AI"):
        self.client = SendGridAPIClient(api_key) if api_key else None
        self.from_email = from_email
        self.from_name = from_name

    async def send_email(self, to_email: str, subject: str, html_content: str, plain_content: str = None) -> dict:
        if not self.client:
            logger.warning("SendGrid not configured, skipping email")
            return {"success": False, "error": "SendGrid not configured"}

        try:
            message = Mail(
                from_email=(self.from_email, self.from_name),
                to_emails=to_email,
                subject=subject,
                html_content=html_content,
                plain_text_content=plain_content,
            )
            response = self.client.send(message)
            logger.info(f"Email sent to {to_email}: {response.status_code}")
            return {"success": True, "status_code": response.status_code}
        except Exception as e:
            logger.error(f"Email send error: {e}")
            return {"success": False, "error": str(e)}
