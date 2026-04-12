"""AI conversation engine using OpenAI GPT-4 with vet-specific prompts and function calling."""

import json
import logging
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI

from src.models.tenant import Clinic
from src.models.conversation import Message

logger = logging.getLogger("vetflow.ai_brain")

# Tool definitions for function calling
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Check available appointment slots for a specific date and service type",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                    "service_type": {"type": "string", "description": "Type of service (e.g., wellness_exam, vaccination, sick_visit, dental, surgery)"},
                },
                "required": ["date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book an appointment for a pet",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner_name": {"type": "string"},
                    "owner_phone": {"type": "string"},
                    "pet_name": {"type": "string"},
                    "pet_species": {"type": "string", "description": "dog, cat, bird, reptile, other"},
                    "service_type": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "time": {"type": "string", "description": "HH:MM in 24h format"},
                    "notes": {"type": "string"},
                },
                "required": ["owner_name", "pet_name", "service_type", "date", "time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "route_to_staff",
            "description": "Transfer the conversation to a human staff member. Use for emergencies or complex requests.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Why the transfer is needed"},
                    "urgent": {"type": "boolean", "description": "True if this is an emergency"},
                },
                "required": ["reason"],
            },
        },
    },
]


class AIBrain:
    """GPT-4 powered conversation engine with vet-specific knowledge."""

    def __init__(self, api_key: str, model: str = "gpt-4", temperature: float = 0.3, max_tokens: int = 500):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def _build_system_prompt(self, clinic: Clinic) -> str:
        hours_str = ""
        for day, times in clinic.business_hours.items():
            if isinstance(times, dict):
                hours_str += f"  {day.capitalize()}: {times.get('open', 'Closed')} - {times.get('close', 'Closed')}\n"

        services_str = ", ".join(clinic.services) if clinic.services else "General veterinary care"

        return f"""You are a friendly, professional AI receptionist for {clinic.name}, a veterinary clinic.

Location: {clinic.address or 'Ask the clinic for directions'}
Phone: {clinic.phone or 'Not available'}
Website: {clinic.website_url or 'Not available'}

Business Hours:
{hours_str or '  Please check with the clinic for hours'}

Services offered: {services_str}

Your responsibilities:
1. SCHEDULING: Help callers book appointments. Always confirm: pet name, species, owner name, phone number, preferred date/time, and reason for visit.
2. INFORMATION: Answer questions about hours, location, services. Be accurate — don't make up pricing.
3. EMERGENCIES: If someone describes a pet emergency (bleeding, seizure, poisoning, difficulty breathing, hit by car, not moving, unconscious), immediately say you'll transfer them to the on-call vet. Use the route_to_staff function with urgent=true.
4. GENERAL: Be warm, empathetic, use the pet's name. Keep responses concise. If you can't help, offer to take a message.

Today's date is {date.today().isoformat()}.
Never make up information you don't have. Say "I'd recommend checking with our team directly" for anything uncertain.
Always use the available functions to check availability before confirming appointment times."""

    async def chat(
        self,
        clinic: Clinic,
        user_message: str,
        history: list[Message],
        tool_handler=None,
    ) -> dict:
        """Process a message and return AI response with any tool calls.

        Returns:
            dict with keys: response (str), tool_calls (list), should_escalate (bool)
        """
        messages = [{"role": "system", "content": self._build_system_prompt(clinic)}]

        for msg in history[-20:]:
            messages.append({"role": msg.role, "content": msg.content})

        messages.append({"role": "user", "content": user_message})

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            choice = response.choices[0]
            tool_calls_results = []
            should_escalate = False

            # Handle tool calls
            if choice.message.tool_calls:
                # Add assistant message with tool calls
                messages.append(choice.message)

                for tc in choice.message.tool_calls:
                    fn_name = tc.function.name
                    fn_args = json.loads(tc.function.arguments)
                    logger.info(f"AI calling tool: {fn_name}({fn_args})")

                    if fn_name == "route_to_staff":
                        should_escalate = True
                        result = {"status": "transferring", "reason": fn_args.get("reason", "")}
                    elif tool_handler:
                        result = await tool_handler(fn_name, fn_args)
                    else:
                        result = {"error": "Tool handler not configured"}

                    tool_calls_results.append({"name": fn_name, "args": fn_args, "result": result})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result),
                    })

                # Get final response after tool calls
                final_response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
                reply = final_response.choices[0].message.content or ""
            else:
                reply = choice.message.content or ""

            return {
                "response": reply,
                "tool_calls": tool_calls_results,
                "should_escalate": should_escalate,
            }

        except Exception as e:
            logger.error(f"AI Brain error: {e}")
            return {
                "response": "I'm sorry, I'm having a little trouble right now. Could you please call us directly or try again in a moment?",
                "tool_calls": [],
                "should_escalate": False,
            }
