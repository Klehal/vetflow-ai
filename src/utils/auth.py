"""API key authentication middleware."""

from fastapi import Request, HTTPException, Depends
from src.models.tenant import Clinic


async def get_current_clinic(request: Request) -> Clinic:
    """Resolve clinic from API key (header, query param, or cookie)."""
    api_key = (
        request.headers.get("X-API-Key")
        or request.query_params.get("api_key")
        or request.cookies.get("api_key")
    )
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")
    tenant_repo = request.app.state.tenant_repo
    clinic = await tenant_repo.get_clinic_by_api_key(api_key)
    if not clinic:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return clinic
