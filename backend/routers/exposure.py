from fastapi import APIRouter, Query
from backend.services import exposure_service

router = APIRouter(prefix="/exposure", tags=["exposure"])

@router.get("/data")
def get_exposure_data(
    years: list[str] | None = Query(None),
    region: list[str] | None = Query(None),
    program: list[str] | None = Query(None)
):
    """Unified data endpoint for Exposure Dashboard."""
    return exposure_service.get_unified_exposure_data(years=years, region=region, program=program)

@router.get("/filters")
def get_filters():
    # Reuse dashboard filters for consistency
    from backend.services import dashboard_service
    return dashboard_service._get_filter_options()

@router.get("/programs")
def program_options():
    return {"programs": exposure_service.get_program_options()}
