"""Bland.ai phone service for voice AI."""

import logging
from typing import Optional

import httpx

logger = logging.getLogger("vetflow.phone")

BLAND_API_BASE = "https://api.bland.ai/v1"


class PhoneService:
    def __init__(self, api_key: str, base_url: str = "http://localhost:8000"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": api_key,
            "Content-Type": "application/json",
        }

    async def create_agent(self, clinic_id: str, clinic_name: str, system_prompt: str, transfer_phone: str = None) -> dict:
        """Register a new Bland.ai agent for a clinic."""
        if not self.api_key:
            return {"success": False, "error": "Bland.ai not configured"}

        payload = {
            "prompt": system_prompt,
            "model": "enhanced",
            "language": "en",
            "voice": "maya",
            "first_sentence": f"Thank you for calling {clinic_name}! How can I help you today?",
            "wait_for_greeting": True,
            "webhook": f"{self.base_url}/webhooks/bland/call-event",
            "tools": [
                {
                    "name": "check_availability",
                    "url": f"{self.base_url}/api/appointments/{clinic_id}/available-slots",
                    "method": "GET",
                },
                {
                    "name": "book_appointment",
                    "url": f"{self.base_url}/api/appointments/{clinic_id}/book",
                    "method": "POST",
                },
            ],
        }

        if transfer_phone:
            payload["transfer_phone_number"] = transfer_phone

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{BLAND_API_BASE}/agents",
                    json=payload,
                    headers=self.headers,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                agent_id = data.get("agent", {}).get("agent_id") or data.get("agent_id")
                logger.info(f"Created Bland.ai agent {agent_id} for clinic {clinic_id}")
                return {"success": True, "agent_id": agent_id, "data": data}
        except Exception as e:
            logger.error(f"Failed to create Bland.ai agent: {e}")
            return {"success": False, "error": str(e)}

    async def handle_call_event(self, payload: dict) -> dict:
        """Process a Bland.ai webhook event."""
        event_type = payload.get("type", "unknown")
        call_id = payload.get("call_id")
        transcript = payload.get("transcripts", [])

        logger.info(f"Bland.ai event: {event_type} for call {call_id}")

        return {
            "event_type": event_type,
            "call_id": call_id,
            "transcript": transcript,
            "duration": payload.get("call_length"),
            "from_number": payload.get("from"),
            "to_number": payload.get("to"),
        }
