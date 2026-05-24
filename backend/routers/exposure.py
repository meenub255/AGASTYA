from fastapi import APIRouter, Query
from backend.services import exposure_service

router = APIRouter(prefix="/exposure", tags=["exposure"])

@router.get("/data")
def get_exposure_data(
    years: list[str] | None = Query(None),
    region: list[str] | None = Query(None),
    program: list[str] | None = Query(None),
    month: list[str] | None = Query(None),
    quarter: list[str] | None = Query(None)
):
    """Unified data endpoint for Exposure Dashboard."""
    return exposure_service.get_unified_exposure_data(years=years, region=region, program=program, month=month, quarter=quarter)

@router.get("/export")
def export_data(
    years: list[str] | None = Query(None),
    region: list[str] | None = Query(None),
    program: list[str] | None = Query(None),
    month: list[str] | None = Query(None),
    quarter: list[str] | None = Query(None)
):
    from backend.services.export_utils import json_to_excel_streaming_response
    data = exposure_service.get_unified_exposure_data(years=years, region=region, program=program, month=month, quarter=quarter)
    # We can export the cohort breakdown or top schools, let's export cohort breakdown table
    return json_to_excel_streaming_response(data["cohort_breakdown"], "exposure_report.xlsx")

@router.get("/filters")
def get_filters():
    # Reuse dashboard filters for consistency
    from backend.services import dashboard_service
    return dashboard_service._get_filter_options()

@router.get("/programs")
def program_options():
    return {"programs": exposure_service.get_program_options()}
