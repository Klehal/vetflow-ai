"""Digital intake form endpoints."""

import json
import logging
import uuid
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader

from src.models.pet import Owner, Pet, IntakeSubmission

logger = logging.getLogger("vetflow.intake")
router = APIRouter()

jinja_env = Environment(loader=FileSystemLoader("src/templates/intake"))


@router.get("/intake/{clinic_id}")
async def intake_form(clinic_id: str, request: Request):
    """Serve the public-facing intake form."""
    tenant_repo = request.app.state.tenant_repo
    clinic = await tenant_repo.get_clinic_by_id(clinic_id)

    if not clinic:
        return HTMLResponse("<h1>Clinic not found</h1>", status_code=404)

    template = jinja_env.get_template("form.html")
    html = template.render(clinic=clinic)
    return HTMLResponse(html)


@router.post("/api/intake/{clinic_id}/submit")
async def submit_intake(clinic_id: str, request: Request):
    """Submit an intake form."""
    tenant_repo = request.app.state.tenant_repo
    pet_repo = request.app.state.pet_repo

    clinic = await tenant_repo.get_clinic_by_id(clinic_id)
    if not clinic:
        return JSONResponse({"error": "Clinic not found"}, status_code=404)

    body = await request.json()

    # Create or find owner
    owner = Owner(
        id=str(uuid.uuid4()),
        clinic_id=clinic_id,
        first_name=body.get("owner_first_name", ""),
        last_name=body.get("owner_last_name", ""),
        phone=body.get("owner_phone"),
        email=body.get("owner_email"),
        address=body.get("owner_address"),
        emergency_contact_name=body.get("emergency_contact_name"),
        emergency_contact_phone=body.get("emergency_contact_phone"),
    )
    await pet_repo.create_owner(owner)

    # Create pet
    pet = Pet(
        id=str(uuid.uuid4()),
        clinic_id=clinic_id,
        owner_id=owner.id,
        name=body.get("pet_name", ""),
        species=body.get("pet_species", ""),
        breed=body.get("pet_breed"),
        date_of_birth=body.get("pet_dob"),
        weight_lbs=body.get("pet_weight"),
        sex=body.get("pet_sex"),
        color=body.get("pet_color"),
        allergies=body.get("pet_allergies"),
        current_medications=body.get("pet_medications"),
        medical_notes=body.get("pet_medical_notes"),
    )
    await pet_repo.create_pet(pet)

    # Save submission
    submission = IntakeSubmission(
        id=str(uuid.uuid4()),
        clinic_id=clinic_id,
        owner_id=owner.id,
        pet_id=pet.id,
        form_data=body,
    )
    await pet_repo.submit_intake(submission)

    logger.info(f"Intake submitted for {owner.full_name} / {pet.name} at clinic {clinic_id}")

    return JSONResponse({
        "success": True,
        "message": f"Thank you, {owner.first_name}! {pet.name}'s information has been submitted.",
        "submission_id": submission.id,
    }, status_code=201)
