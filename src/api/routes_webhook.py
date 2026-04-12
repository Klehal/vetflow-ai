"""Webhook endpoints for Bland.ai (phone) and Twilio (SMS)."""

import json
import logging
import uuid
from fastapi import APIRouter, Request, Form
from fastapi.responses import JSONResponse, Response

from src.models.conversation import Conversation, Message, Channel

logger = logging.getLogger("vetflow.webhooks")
router = APIRouter()


@router.post("/webhooks/bland/call-event")
async def bland_call_event(request: Request):
    """Handle Bland.ai call webhook events."""
    app = request.app
    payload = await request.json()

    phone_service = app.state.phone_service
    conv_repo = app.state.conv_repo
    tenant_repo = app.state.tenant_repo

    event = await phone_service.handle_call_event(payload)

    # Find clinic by the phone number called
    to_number = event.get("to_number")
    if to_number:
        clinic = await tenant_repo.get_clinic_by_twilio_phone(to_number)
        if clinic:
            conv = Conversation(
                id=str(uuid.uuid4()),
                clinic_id=clinic.id,
                channel=Channel.PHONE,
                external_id=event.get("call_id"),
                caller_phone=event.get("from_number"),
                status="resolved" if event["event_type"] == "call.ended" else "active",
            )
            await conv_repo.create_conversation(conv)

            # Store transcript as messages
            for turn in event.get("transcript", []):
                msg = Message(
                    id=str(uuid.uuid4()),
                    conversation_id=conv.id,
                    role="user" if turn.get("user") else "assistant",
                    content=turn.get("user") or turn.get("agent", ""),
                    channel=Channel.PHONE,
                    metadata={"call_id": event.get("call_id")},
                )
                await conv_repo.add_message(msg)

    return JSONResponse({"status": "ok"})


@router.post("/webhooks/twilio/sms")
async def twilio_sms_webhook(request: Request):
    """Handle inbound SMS from Twilio."""
    app = request.app
    form = await request.form()

    from_number = form.get("From", "")
    to_number = form.get("To", "")
    body = form.get("Body", "").strip()

    logger.info(f"Inbound SMS from {from_number} to {to_number}: {body[:50]}")

    tenant_repo = app.state.tenant_repo
    conv_repo = app.state.conv_repo
    ai_brain = app.state.ai_brain
    sms_service = app.state.sms_service
    appt_service = app.state.appt_service

    clinic = await tenant_repo.get_clinic_by_twilio_phone(to_number)
    if not clinic:
        logger.warning(f"No clinic found for Twilio number {to_number}")
        return Response(content="<Response></Response>", media_type="application/xml")

    # Find or create conversation
    conv = await conv_repo.get_active_conversation(clinic.id, from_number, Channel.SMS)
    if not conv:
        conv = Conversation(
            id=str(uuid.uuid4()),
            clinic_id=clinic.id,
            channel=Channel.SMS,
            caller_phone=from_number,
        )
        await conv_repo.create_conversation(conv)

    # Store inbound message
    user_msg = Message(
        id=str(uuid.uuid4()),
        conversation_id=conv.id,
        role="user",
        content=body,
        channel=Channel.SMS,
    )
    await conv_repo.add_message(user_msg)

    # Handle quick replies
    if body.upper() == "CONFIRM":
        reply_text = "Thanks for confirming your appointment! We'll see you soon."
    elif body.upper() in ("CANCEL", "STOP"):
        reply_text = "We've noted your cancellation request. Please call us if you need to reschedule."
    else:
        # Run through AI Brain
        history = await conv_repo.get_recent_messages(conv.id, limit=10)

        async def handle_tool(fn_name, fn_args):
            if fn_name == "check_availability":
                slots = await appt_service.get_available_slots(clinic, fn_args["date"])
                return {"available_slots": [{"time": s.time} for s in slots if s.available][:5]}
            elif fn_name == "book_appointment":
                return await appt_service.book_appointment(
                    clinic=clinic, owner_name=fn_args.get("owner_name", ""),
                    pet_name=fn_args.get("pet_name", ""), service_type=fn_args.get("service_type", "general"),
                    target_date=fn_args["date"], target_time=fn_args["time"],
                    owner_phone=from_number, source="sms",
                )
            return {}

        result = await ai_brain.chat(clinic, body, history, tool_handler=handle_tool)
        reply_text = result["response"]

    # Store and send reply
    reply_msg = Message(
        id=str(uuid.uuid4()),
        conversation_id=conv.id,
        role="assistant",
        content=reply_text,
        channel=Channel.SMS,
    )
    await conv_repo.add_message(reply_msg)

    if clinic.twilio_phone:
        await sms_service.send_sms(from_number, reply_text, clinic.twilio_phone)

    # Return TwiML empty response (we send reply via API instead)
    return Response(content="<Response></Response>", media_type="application/xml")
