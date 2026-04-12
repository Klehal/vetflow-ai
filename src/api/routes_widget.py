"""Serve the embeddable chat widget."""

import logging
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

logger = logging.getLogger("vetflow.widget")
router = APIRouter()


@router.get("/widget/{clinic_id}/chat-widget.js")
async def serve_widget(clinic_id: str, request: Request):
    """Serve the chat widget JavaScript file."""
    return FileResponse(
        "src/widget/chat-widget.js",
        media_type="application/javascript",
        headers={"Access-Control-Allow-Origin": "*"},
    )


@router.get("/widget/{clinic_id}/config")
async def widget_config(clinic_id: str, request: Request):
    """Return widget configuration for a clinic."""
    tenant_repo = request.app.state.tenant_repo
    clinic = await tenant_repo.get_clinic_by_id(clinic_id)

    if not clinic:
        return JSONResponse({"error": "Clinic not found"}, status_code=404)

    base_url = request.app.state.config["_env"]["base_url"]

    return JSONResponse({
        "clinic_id": clinic.id,
        "clinic_name": clinic.name,
        "greeting": clinic.widget_greeting,
        "primary_color": clinic.widget_primary_color,
        "ws_url": f"ws{'s' if 'https' in base_url else ''}://{base_url.replace('https://', '').replace('http://', '')}/ws/chat/{clinic.id}",
        "http_url": f"{base_url}/api/chat/{clinic.id}/message",
    })
