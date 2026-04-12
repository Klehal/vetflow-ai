"""Appointment booking API endpoints."""

import logging
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import JSONResponse
from src.utils.auth import get_current_clinic

logger = logging.getLogger("vetflow.api.appointments")
router = APIRouter()


@router.get("/api/appointments/{clinic_id}/available-slots")
async def get_available_slots(clinic_id: str, request: Request, date: str = Query(...), service_type: str = Query(None)):
    """Get available appointment slots for a date."""
    appt_service = request.app.state.appt_service
    tenant_repo = request.app.state.tenant_repo

    clinic = await tenant_repo.get_clinic_by_id(clinic_id)
    if not clinic:
        return JSONResponse({"error": "Clinic not found"}, status_code=404)

    slots = await appt_service.get_available_slots(clinic, date, service_type)
    available = [{"date": s.date, "time": s.time, "duration": s.duration_minutes} for s in slots if s.available]

    return JSONResponse({"date": date, "available_slots": available})


@router.post("/api/appointments/{clinic_id}/book")
async def book_appointment(clinic_id: str, request: Request):
    """Book a new appointment."""
    appt_service = request.app.state.appt_service
    tenant_repo = request.app.state.tenant_repo

    clinic = await tenant_repo.get_clinic_by_id(clinic_id)
    if not clinic:
        return JSONResponse({"error": "Clinic not found"}, status_code=404)

    body = await request.json()

    result = await appt_service.book_appointment(
        clinic=clinic,
        owner_name=body.get("owner_name", ""),
        pet_name=body.get("pet_name", ""),
        service_type=body.get("service_type", "general"),
        target_date=body["date"],
        target_time=body["time"],
        owner_phone=body.get("owner_phone"),
        owner_email=body.get("owner_email"),
        pet_species=body.get("pet_species"),
        notes=body.get("notes"),
        source=body.get("source", "web"),
    )

    status_code = 201 if result["success"] else 409
    return JSONResponse(result, status_code=status_code)


@router.patch("/api/appointments/{appt_id}/cancel")
async def cancel_appointment(appt_id: str, request: Request):
    """Cancel an appointment."""
    appt_service = request.app.state.appt_service
    result = await appt_service.cancel_appointment(appt_id)
    status_code = 200 if result["success"] else 404
    return JSONResponse(result, status_code=status_code)


@router.get("/api/appointments/{clinic_id}/list")
async def list_appointments(clinic_id: str, request: Request, start_date: str = Query(...), end_date: str = Query(None)):
    """List appointments for a date range."""
    appt_repo = request.app.state.appt_repo
    end = end_date or start_date
    appts = await appt_repo.get_appointments_range(clinic_id, start_date, end)
    return JSONResponse({
        "appointments": [
            {
                "id": a.id, "owner_name": a.owner_name, "pet_name": a.pet_name,
                "service_type": a.service_type, "date": a.scheduled_date,
                "time": a.scheduled_time, "status": a.status, "source": a.source,
            }
            for a in appts
        ]
    })
