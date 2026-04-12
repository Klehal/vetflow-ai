"""Clinic owner dashboard endpoints."""

import logging
from datetime import date, timedelta
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader

from src.utils.auth import get_current_clinic

logger = logging.getLogger("vetflow.dashboard")
router = APIRouter()

jinja_env = Environment(loader=FileSystemLoader("src/templates/dashboard"))


@router.get("/dashboard/")
async def dashboard_overview(request: Request):
    """Main dashboard page."""
    try:
        clinic = await get_current_clinic(request)
    except Exception:
        return HTMLResponse("<h1>Please provide your API key</h1><p>Add ?api_key=YOUR_KEY or set the X-API-Key header.</p>", status_code=401)

    app = request.app
    appt_repo = app.state.appt_repo
    conv_repo = app.state.conv_repo
    pet_repo = app.state.pet_repo

    today = date.today().isoformat()
    week_end = (date.today() + timedelta(days=7)).isoformat()

    appointments_today = await appt_repo.get_appointments_by_date(clinic.id, today)
    appointments_week = await appt_repo.get_appointments_range(clinic.id, today, week_end)
    conversations = await conv_repo.get_conversations_by_clinic(clinic.id, limit=20)
    intake_submissions = await pet_repo.get_intake_submissions(clinic.id, status="pending")

    template = jinja_env.get_template("overview.html")
    html = template.render(
        clinic=clinic,
        appointments_today=appointments_today,
        appointments_week=appointments_week,
        conversations=conversations,
        pending_intakes=intake_submissions,
        today=today,
    )
    return HTMLResponse(html)


@router.get("/dashboard/appointments")
async def dashboard_appointments(request: Request):
    """Appointments page."""
    clinic = await get_current_clinic(request)
    appt_repo = request.app.state.appt_repo

    today = date.today().isoformat()
    month_end = (date.today() + timedelta(days=30)).isoformat()
    appointments = await appt_repo.get_appointments_range(clinic.id, today, month_end)

    template = jinja_env.get_template("appointments.html")
    html = template.render(clinic=clinic, appointments=appointments)
    return HTMLResponse(html)


@router.get("/dashboard/conversations")
async def dashboard_conversations(request: Request):
    """Conversations page."""
    clinic = await get_current_clinic(request)
    conv_repo = request.app.state.conv_repo

    conversations = await conv_repo.get_conversations_by_clinic(clinic.id, limit=50)

    # Load messages for each conversation
    conv_with_msgs = []
    for conv in conversations[:20]:
        msgs = await conv_repo.get_messages(conv.id, limit=30)
        conv_with_msgs.append({"conversation": conv, "messages": msgs})

    template = jinja_env.get_template("conversations.html")
    html = template.render(clinic=clinic, conversations=conv_with_msgs)
    return HTMLResponse(html)


@router.get("/dashboard/intake")
async def dashboard_intake(request: Request):
    """Intake submissions page."""
    clinic = await get_current_clinic(request)
    pet_repo = request.app.state.pet_repo
    submissions = await pet_repo.get_intake_submissions(clinic.id)

    template = jinja_env.get_template("intake.html")
    html = template.render(clinic=clinic, submissions=submissions)
    return HTMLResponse(html)


@router.get("/api/dashboard/{clinic_id}/stats")
async def dashboard_stats(clinic_id: str, request: Request):
    """JSON stats for AJAX dashboard updates."""
    appt_repo = request.app.state.appt_repo
    conv_repo = request.app.state.conv_repo

    today = date.today().isoformat()
    appts = await appt_repo.get_appointments_by_date(clinic_id, today)
    convs = await conv_repo.get_conversations_by_clinic(clinic_id, limit=100)

    today_convs = [c for c in convs if c.started_at and c.started_at.startswith(today)]

    return JSONResponse({
        "appointments_today": len(appts),
        "conversations_today": len(today_convs),
        "phone_calls": len([c for c in today_convs if c.channel == "phone"]),
        "chats": len([c for c in today_convs if c.channel == "chat"]),
        "sms": len([c for c in today_convs if c.channel == "sms"]),
    })
