"""Chat widget WebSocket and HTTP endpoints."""

import json
import logging
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse

from src.models.conversation import Conversation, Message, Channel

logger = logging.getLogger("vetflow.chat")
router = APIRouter()


@router.websocket("/ws/chat/{clinic_id}")
async def chat_websocket(websocket: WebSocket, clinic_id: str):
    """WebSocket endpoint for real-time chat."""
    await websocket.accept()

    app = websocket.app
    tenant_repo = app.state.tenant_repo
    conv_repo = app.state.conv_repo
    ai_brain = app.state.ai_brain
    appt_service = app.state.appt_service

    clinic = await tenant_repo.get_clinic_by_id(clinic_id)
    if not clinic:
        await websocket.send_json({"error": "Clinic not found"})
        await websocket.close()
        return

    # Create conversation
    conv = Conversation(
        id=str(uuid.uuid4()),
        clinic_id=clinic_id,
        channel=Channel.CHAT,
    )
    await conv_repo.create_conversation(conv)

    # Send greeting
    greeting = clinic.widget_greeting
    await websocket.send_json({"type": "message", "role": "assistant", "content": greeting})

    greeting_msg = Message(
        id=str(uuid.uuid4()),
        conversation_id=conv.id,
        role="assistant",
        content=greeting,
        channel=Channel.CHAT,
    )
    await conv_repo.add_message(greeting_msg)

    # Tool handler for AI function calls
    async def handle_tool(fn_name: str, fn_args: dict) -> dict:
        if fn_name == "check_availability":
            slots = await appt_service.get_available_slots(
                clinic, fn_args["date"], fn_args.get("service_type")
            )
            available = [{"time": s.time, "available": s.available} for s in slots if s.available]
            return {"available_slots": available[:8], "date": fn_args["date"]}

        elif fn_name == "book_appointment":
            result = await appt_service.book_appointment(
                clinic=clinic,
                owner_name=fn_args.get("owner_name", ""),
                pet_name=fn_args.get("pet_name", ""),
                service_type=fn_args.get("service_type", "general"),
                target_date=fn_args["date"],
                target_time=fn_args["time"],
                owner_phone=fn_args.get("owner_phone"),
                pet_species=fn_args.get("pet_species"),
                notes=fn_args.get("notes"),
                source="chat",
            )
            return result

        return {"error": f"Unknown tool: {fn_name}"}

    try:
        while True:
            data = await websocket.receive_text()
            msg_data = json.loads(data)
            user_text = msg_data.get("content", "").strip()

            if not user_text:
                continue

            # Store user message
            user_msg = Message(
                id=str(uuid.uuid4()),
                conversation_id=conv.id,
                role="user",
                content=user_text,
                channel=Channel.CHAT,
            )
            await conv_repo.add_message(user_msg)

            # Send typing indicator
            await websocket.send_json({"type": "typing", "typing": True})

            # Get AI response
            history = await conv_repo.get_recent_messages(conv.id, limit=20)
            result = await ai_brain.chat(clinic, user_text, history, tool_handler=handle_tool)

            # Store and send assistant response
            assistant_msg = Message(
                id=str(uuid.uuid4()),
                conversation_id=conv.id,
                role="assistant",
                content=result["response"],
                channel=Channel.CHAT,
                metadata={"tool_calls": result.get("tool_calls", [])},
            )
            await conv_repo.add_message(assistant_msg)

            await websocket.send_json({
                "type": "message",
                "role": "assistant",
                "content": result["response"],
            })

            if result.get("should_escalate"):
                await websocket.send_json({
                    "type": "escalation",
                    "message": "Transferring you to a staff member...",
                })

    except WebSocketDisconnect:
        logger.info(f"Chat disconnected for conversation {conv.id}")
        await conv_repo.end_conversation(conv.id)


@router.post("/api/chat/{clinic_id}/message")
async def chat_http_fallback(clinic_id: str, request: Request):
    """HTTP fallback for chat when WebSocket isn't available."""
    app = request.app
    body = await request.json()

    tenant_repo = app.state.tenant_repo
    conv_repo = app.state.conv_repo
    ai_brain = app.state.ai_brain
    appt_service = app.state.appt_service

    clinic = await tenant_repo.get_clinic_by_id(clinic_id)
    if not clinic:
        return JSONResponse({"error": "Clinic not found"}, status_code=404)

    conv_id = body.get("conversation_id")
    user_text = body.get("content", "").strip()

    if not conv_id:
        conv = Conversation(id=str(uuid.uuid4()), clinic_id=clinic_id, channel=Channel.CHAT)
        await conv_repo.create_conversation(conv)
        conv_id = conv.id

    user_msg = Message(id=str(uuid.uuid4()), conversation_id=conv_id, role="user", content=user_text, channel=Channel.CHAT)
    await conv_repo.add_message(user_msg)

    history = await conv_repo.get_recent_messages(conv_id, limit=20)

    async def handle_tool(fn_name, fn_args):
        if fn_name == "check_availability":
            slots = await appt_service.get_available_slots(clinic, fn_args["date"], fn_args.get("service_type"))
            return {"available_slots": [{"time": s.time} for s in slots if s.available][:8]}
        elif fn_name == "book_appointment":
            return await appt_service.book_appointment(
                clinic=clinic, owner_name=fn_args.get("owner_name", ""), pet_name=fn_args.get("pet_name", ""),
                service_type=fn_args.get("service_type", "general"), target_date=fn_args["date"],
                target_time=fn_args["time"], owner_phone=fn_args.get("owner_phone"),
                pet_species=fn_args.get("pet_species"), source="chat",
            )
        return {"error": f"Unknown tool: {fn_name}"}

    result = await ai_brain.chat(clinic, user_text, history, tool_handler=handle_tool)

    assistant_msg = Message(id=str(uuid.uuid4()), conversation_id=conv_id, role="assistant", content=result["response"], channel=Channel.CHAT)
    await conv_repo.add_message(assistant_msg)

    return JSONResponse({
        "conversation_id": conv_id,
        "response": result["response"],
        "should_escalate": result.get("should_escalate", False),
    })
